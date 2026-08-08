"""AI assistant helpers (no Ollama network required)."""
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

from btf_viewer_pkg.ai_assistant import (  # noqa: E402
    AI_PRESET_CUSTOM,
    AI_PRESET_GEMINI,
    AI_PRESET_OLLAMA,
    AI_PRESET_OPENAI,
    AI_TEMPLATE_QUESTIONS,
    DEFAULT_AI_BASE_URL,
    DEFAULT_AI_PRESET,
    _format_ai_log_html,
    apply_ai_preset,
    build_ai_system_prompt,
    build_ai_user_message,
    extract_jump_times,
    format_ai_conversation_html,
    format_ai_conversation_markdown,
    format_ai_conversation_text,
    is_local_ai_host,
    markdown_to_safe_html,
    match_model_name,
    migrate_ai_settings,
    normalize_ai_base_url,
    normalize_ai_context,
    normalize_ai_preset,
    parse_ai_settings_json,
    resolve_ai_settings,
)


class AiAssistantHelpersTests(unittest.TestCase):
    def test_templates_nonempty(self) -> None:
        self.assertGreaterEqual(len(AI_TEMPLATE_QUESTIONS), 5)
        ids = [t[0] for t in AI_TEMPLATE_QUESTIONS]
        self.assertEqual(ids[0], "findings")
        self.assertEqual(AI_TEMPLATE_QUESTIONS[0][1], "Analysis Findings")
        self.assertEqual(ids[1], "compare")
        self.assertEqual(AI_TEMPLATE_QUESTIONS[1][1], "Trace Compare")
        self.assertIn("triage", ids)
        self.assertIn("migrations", ids)

    def test_normalize_ai_base_url(self) -> None:
        self.assertEqual(
            normalize_ai_base_url("http://localhost:11434"),
            "http://localhost:11434/v1",
        )
        self.assertEqual(
            normalize_ai_base_url("http://localhost:11434/api"),
            "http://localhost:11434/v1",
        )
        self.assertEqual(
            normalize_ai_base_url("https://api.openai.com/v1/chat/completions"),
            "https://api.openai.com/v1",
        )
        self.assertEqual(normalize_ai_base_url(""), DEFAULT_AI_BASE_URL)

    def test_normalize_ai_preset(self) -> None:
        self.assertEqual(normalize_ai_preset(None), DEFAULT_AI_PRESET)
        self.assertEqual(normalize_ai_preset("ollama"), AI_PRESET_OLLAMA)
        self.assertEqual(normalize_ai_preset("gemini"), AI_PRESET_GEMINI)
        self.assertEqual(normalize_ai_preset("openai"), AI_PRESET_OPENAI)
        self.assertEqual(normalize_ai_preset("chatgpt"), AI_PRESET_OPENAI)
        # Retired presets (xAI, DeepSeek) land on Custom.
        self.assertEqual(normalize_ai_preset("deepseek"), AI_PRESET_CUSTOM)

    def test_apply_ai_preset(self) -> None:
        ollama = apply_ai_preset(AI_PRESET_OLLAMA)
        self.assertEqual(ollama["preset"], AI_PRESET_OLLAMA)
        self.assertEqual(ollama["base_url"], "http://localhost:11434/v1")
        gem = apply_ai_preset(AI_PRESET_GEMINI)
        self.assertIn("generativelanguage", gem["base_url"])
        self.assertEqual(gem["model"], "gemini-flash-lite-latest")
        oai = apply_ai_preset(AI_PRESET_OPENAI)
        self.assertEqual(oai["base_url"], "https://api.openai.com/v1")
        self.assertTrue(oai["model"])

    def test_resolve_ai_settings_per_preset(self) -> None:
        cfg = {
            "preset": AI_PRESET_GEMINI,
            "ollama_model": "llama3.2:3b",
            "gemini_api_key": "k",
        }
        active = resolve_ai_settings(cfg)
        self.assertEqual(active["preset"], AI_PRESET_GEMINI)
        self.assertEqual(active["api_key"], "k")
        self.assertEqual(active["model"], "gemini-flash-lite-latest")
        other = resolve_ai_settings(cfg, AI_PRESET_OLLAMA)
        self.assertEqual(other["model"], "llama3.2:3b")
        self.assertEqual(other["api_key"], "")

    def test_migrate_legacy_ai_settings(self) -> None:
        patch = migrate_ai_settings({
            "provider": "openai_compatible",
            "openai_preset": "gemini",
            "openai_base_url": "https://generativelanguage.googleapis.com/v1beta/openai",
            "openai_model": "gemini-3.6-flash",
            "openai_api_key": "cloud-key",
            "ollama_url": "http://localhost:11434",
            "ollama_model": "phi4-mini:3.8b",
        })
        self.assertEqual(patch["preset"], AI_PRESET_GEMINI)
        self.assertEqual(patch["gemini_model"], "gemini-3.6-flash")
        self.assertEqual(patch["gemini_api_key"], "cloud-key")
        self.assertEqual(patch["ollama_base_url"], "http://localhost:11434/v1")
        # The retired openai_* fields held Gemini values, so they are cleared.
        self.assertEqual(patch["openai_model"], "")
        self.assertEqual(patch["openai_api_key"], "")
        # A settings dict already in the new shape needs no patch, even though
        # its openai_* keys look like the old ones.
        self.assertEqual(migrate_ai_settings({
            "preset": AI_PRESET_OPENAI,
            "openai_base_url": "https://api.openai.com/v1",
            "openai_api_key": "sk-keep",
        }), {})
        # An old OpenAI setup keeps its fields under the OpenAI preset.
        legacy_openai = migrate_ai_settings({
            "provider": "openai_compatible",
            "openai_preset": "openai",
            "openai_base_url": "https://api.openai.com/v1",
            "openai_api_key": "sk-keep",
        })
        self.assertEqual(legacy_openai["preset"], AI_PRESET_OPENAI)
        self.assertEqual(legacy_openai["openai_base_url"], "https://api.openai.com/v1")
        self.assertNotIn("openai_api_key", legacy_openai)
        # An old xAI setup becomes Custom and vacates the openai_* keys.
        legacy_xai = migrate_ai_settings({
            "provider": "openai_compatible",
            "openai_preset": "xai",
            "openai_base_url": "https://api.x.ai/v1",
            "openai_api_key": "xai-key",
        })
        self.assertEqual(legacy_xai["preset"], AI_PRESET_CUSTOM)
        self.assertEqual(legacy_xai["custom_base_url"], "https://api.x.ai/v1")
        self.assertEqual(legacy_xai["custom_api_key"], "xai-key")
        self.assertEqual(legacy_xai["openai_base_url"], "")
        self.assertEqual(legacy_xai["openai_api_key"], "")

    def test_parse_ai_settings_json(self) -> None:
        patch = parse_ai_settings_json(
            '{"preset": "gemini",'
            ' "base_url": "https://generativelanguage.googleapis.com/v1beta/openai",'
            ' "model": "gemini-flash-lite-latest", "api_key": "",'
            ' "response_language": "English"}'
        )
        self.assertEqual(patch["preset"], AI_PRESET_GEMINI)
        self.assertEqual(patch["gemini_model"], "gemini-flash-lite-latest")
        self.assertEqual(patch["response_language"], "English")
        # An empty key means "fall back to the environment", so nothing is written.
        self.assertNotIn("gemini_api_key", patch)

    def test_parse_ai_settings_json_shapes(self) -> None:
        # camelCase keys import too.
        openai = parse_ai_settings_json({
            "preset": "openai",
            "baseUrl": "https://api.openai.com",
            "model": "gpt-4o-mini",
            "apiKey": "Bearer sk-test",
        })
        self.assertEqual(openai["preset"], AI_PRESET_OPENAI)
        self.assertEqual(openai["openai_base_url"], "https://api.openai.com/v1")
        self.assertEqual(openai["openai_api_key"], "sk-test")
        # A retired vendor name lands on Custom.
        xai = parse_ai_settings_json({
            "preset": "xai",
            "base_url": "https://api.x.ai/v1",
            "model": "grok-2",
        })
        self.assertEqual(xai["preset"], AI_PRESET_CUSTOM)
        self.assertEqual(xai["custom_model"], "grok-2")
        # No preset given: inferred from the base URL.
        local = parse_ai_settings_json({"base_url": "http://localhost:11434"})
        self.assertEqual(local["preset"], AI_PRESET_OLLAMA)
        self.assertEqual(local["ollama_base_url"], "http://localhost:11434/v1")
        # Several endpoints in one file.
        multi = parse_ai_settings_json({
            "preset": "ollama",
            "presets": {"gemini": {"api_key": "k"}, "ollama": {"model": "m"}},
        })
        self.assertEqual(multi["preset"], AI_PRESET_OLLAMA)
        self.assertEqual(multi["gemini_api_key"], "k")
        self.assertEqual(multi["ollama_model"], "m")

    def test_parse_ai_settings_json_errors(self) -> None:
        for bad in (
            "not json",
            "[]",
            '{"preset": "claude"}',
            '{"model": ""}',
            '{"preset": "custom", "model": "m"}',
            '{"base_url": "ftp://example.com"}',
        ):
            with self.assertRaises(ValueError):
                parse_ai_settings_json(bad)

    def test_example_ai_settings_files_import(self) -> None:
        here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        expected = {
            "gemini.json": AI_PRESET_GEMINI,
            "openai.json": AI_PRESET_OPENAI,
            "deepseek.json": AI_PRESET_CUSTOM,
            "grok.json": AI_PRESET_CUSTOM,
        }
        for name, preset in expected.items():
            path = os.path.join(here, "examples", "ai", name)
            with open(path, encoding="utf-8") as fh:
                patch = parse_ai_settings_json(fh.read())
            self.assertEqual(patch["preset"], preset, name)
            self.assertTrue(patch[f"{preset}_base_url"], name)
            self.assertTrue(patch[f"{preset}_model"], name)

    def test_normalize_api_key(self) -> None:
        from btf_viewer_pkg.ai_assistant import ai_request_headers, normalize_api_key
        self.assertEqual(normalize_api_key("  Bearer AIzaSyAbc  "), "AIzaSyAbc")
        self.assertEqual(normalize_api_key('"AIzaSyAbc"'), "AIzaSyAbc")
        self.assertEqual(normalize_api_key("GEMINI_API_KEY"), "")
        # Smart quotes / CJK junk must not reach HTTP headers (web fetch).
        self.assertEqual(normalize_api_key("“AIzaSyAbc”"), "AIzaSyAbc")
        self.assertEqual(normalize_api_key("AIza密鑰SyAbc"), "AIzaSyAbc")
        headers = ai_request_headers(
            "AIzaSyAbc",
            base_url="https://generativelanguage.googleapis.com/v1beta/openai",
        )
        self.assertEqual(headers["Authorization"], "Bearer AIzaSyAbc")
        self.assertNotIn("x-goog-api-key", headers)

    def test_openai_http_429_tip(self) -> None:
        from btf_viewer_pkg.ai_assistant import _ai_http_error_tip
        tip = _ai_http_error_tip(
            429, "RESOURCE_EXHAUSTED",
            base_url="https://generativelanguage.googleapis.com/v1beta/openai",
        )
        self.assertIn("quota", tip.lower())
        self.assertIn("gemini-flash-lite-latest", tip)

    def test_match_model_name(self) -> None:
        served = ["qwen2.5:14b", "deepseek-r1:14b", "llama3.2:latest"]
        self.assertEqual(match_model_name("qwen2.5:14b", served), "qwen2.5:14b")
        self.assertEqual(match_model_name("qwen2.5", served), "qwen2.5:14b")
        self.assertIsNone(match_model_name("missing", served))

    def test_match_model_name_gemini_namespace(self) -> None:
        # Gemini lists ids as models/<id>; the chat API takes either form.
        served = ["models/gemini-flash-lite-latest", "models/gemini-2.5-pro"]
        self.assertEqual(
            match_model_name("gemini-flash-lite-latest", served),
            "models/gemini-flash-lite-latest",
        )
        self.assertEqual(
            match_model_name("models/gemini-2.5-pro", served),
            "models/gemini-2.5-pro",
        )
        self.assertIsNone(match_model_name("gemini-9.9-pro", served))

    def test_user_message_includes_findings(self) -> None:
        msg = build_ai_user_message(
            "Why thrash?",
            findings_text="1. [WARNING] Thrashing\n   CS[22] migrates heavily",
            span="2.358 s",
            cores=8,
            scope="(cursor range)",
        )
        self.assertIn("Thrashing", msg)
        self.assertIn("Why thrash?", msg)
        self.assertIn("2.358 s", msg)
        self.assertIn("(cursor range)", msg)

    def test_extract_jump_times(self) -> None:
        self.assertEqual(extract_jump_times("see jump:1805120 and jump:99.5"), [1805120.0, 99.5])
        self.assertEqual(extract_jump_times("no jumps here"), [])

    def test_format_ai_log_html_links(self) -> None:
        html_out = _format_ai_log_html("assistant", "Open jump:1805120 next")
        self.assertIn('href="btfjump:1805120"', html_out)
        self.assertIn(">jump:1805120</a>", html_out)
        self.assertIn("<b>Assistant:</b>", html_out)
        # User text is escaped (no raw tags).
        esc = _format_ai_log_html("user", "<script>x</script>")
        self.assertIn("&lt;script&gt;", esc)
        self.assertNotIn("<script>", esc)

    def test_markdown_to_safe_html(self) -> None:
        html_out = markdown_to_safe_html(
            "## Title\n\n"
            "See **bold** and `code`, then jump:42.\n\n"
            "- item one\n"
            "- item two\n\n"
            "```\nraw <tag>\n```\n"
        )
        self.assertIn("<h2>", html_out)
        self.assertIn("<strong>bold</strong>", html_out)
        self.assertIn("<code>code</code>", html_out)
        self.assertIn('href="btfjump:42"', html_out)
        self.assertIn("<ul>", html_out)
        self.assertIn("&lt;tag&gt;", html_out)
        self.assertNotIn("<tag>", html_out)
        # Unsafe raw HTML is escaped.
        unsafe = markdown_to_safe_html("<script>alert(1)</script>")
        self.assertIn("&lt;script&gt;", unsafe)
        self.assertNotIn("<script>", unsafe)

    def test_normalize_ai_context_accepts_camel_case(self) -> None:
        ctx = normalize_ai_context({
            "findingsText": "hello",
            "span": "1 s",
            "cores": 2,
            "scope": "full",
        })
        self.assertEqual(ctx["findings_text"], "hello")
        self.assertEqual(ctx["span"], "1 s")
        self.assertEqual(ctx["cores"], 2)
        snake = normalize_ai_context({"findings_text": "x"})
        self.assertEqual(snake["findings_text"], "x")

    def test_conversation_export_formats(self) -> None:
        entries = [
            ("user", "Why is CS[22] late?"),
            ("assistant", "## Answer\n\nIt migrates at jump:1805000."),
        ]
        md = format_ai_conversation_markdown(entries)
        self.assertTrue(md.startswith("# BTF Viewer — AI Conversation"))
        self.assertIn("## You\n\nWhy is CS[22] late?", md)
        self.assertIn("## Assistant\n\n## Answer", md)
        self.assertTrue(md.endswith("\n"))
        txt = format_ai_conversation_text(entries)
        self.assertIn("You:\nWhy is CS[22] late?", txt)
        self.assertIn("Assistant:\n## Answer", txt)
        self.assertNotIn("<", txt)

    def test_conversation_export_html(self) -> None:
        """HTML export is a standalone document, not Qt's editor markup."""
        entries = [
            ("user", "Why is <CS[22]> late?"),
            ("assistant", "## Answer\n\nIt migrates at jump:1805000."),
        ]
        doc = format_ai_conversation_html(entries)
        self.assertTrue(doc.startswith("<!DOCTYPE html>"))
        self.assertIn("<title>BTF Viewer — AI Conversation</title>", doc)
        self.assertIn('<section class="msg user"><h3>You</h3>', doc)
        self.assertIn('<section class="msg assistant"><h3>Assistant</h3>', doc)
        # Assistant Markdown is rendered; user text is escaped.
        self.assertIn("<h2>Answer</h2>", doc)
        self.assertIn("&lt;CS[22]&gt;", doc)
        self.assertIn('href="btfjump:1805000"', doc)
        # No duplicated role prefix from the log formatter.
        self.assertNotIn("<b>Assistant:</b>", doc)

    def test_is_local_ai_host(self) -> None:
        for url in (
            "http://localhost:11434/v1",
            "http://127.0.0.1:11434/v1",
            "http://0.0.0.0:11434/v1",
            "http://[::1]:11434/v1",
            "http://host.docker.internal:11434/v1",
            "localhost:11434/v1",
        ):
            self.assertTrue(is_local_ai_host(url), url)
        for url in (
            "https://api.openai.com/v1",
            "https://generativelanguage.googleapis.com/v1beta/openai",
            "http://localhost.example.com/v1",
        ):
            self.assertFalse(is_local_ai_host(url), url)

    def test_system_prompt_language(self) -> None:
        en = build_ai_system_prompt("English")
        self.assertIn("Always write your entire reply in English.", en)
        zh = build_ai_system_prompt("Traditional Chinese (繁體中文)")
        self.assertIn("Traditional Chinese (繁體中文)", zh)


if __name__ == "__main__":
    unittest.main()
