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
    AI_PROVIDER_OLLAMA,
    AI_PROVIDER_OPENAI,
    AI_TEMPLATE_QUESTIONS,
    DEFAULT_OPENAI_BASE_URL,
    _format_ai_log_html,
    apply_openai_preset,
    build_ai_system_prompt,
    build_ai_user_message,
    extract_jump_times,
    markdown_to_safe_html,
    match_ollama_model,
    normalize_ai_context,
    normalize_ai_provider,
    normalize_ollama_url,
    normalize_openai_base_url,
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

    def test_normalize_url(self) -> None:
        self.assertEqual(normalize_ollama_url("http://localhost:11434/"), "http://localhost:11434")
        self.assertEqual(normalize_ollama_url(""), "http://localhost:11434")

    def test_normalize_ai_provider(self) -> None:
        self.assertEqual(normalize_ai_provider(None), AI_PROVIDER_OLLAMA)
        self.assertEqual(normalize_ai_provider("ollama"), AI_PROVIDER_OLLAMA)
        self.assertEqual(normalize_ai_provider("openai"), AI_PROVIDER_OPENAI)
        self.assertEqual(normalize_ai_provider("OpenAI-compatible"), AI_PROVIDER_OPENAI)

    def test_normalize_openai_base_url(self) -> None:
        self.assertEqual(
            normalize_openai_base_url("https://api.openai.com/v1/"),
            "https://api.openai.com/v1",
        )
        self.assertEqual(
            normalize_openai_base_url("https://api.openai.com"),
            "https://api.openai.com/v1",
        )
        self.assertEqual(
            normalize_openai_base_url("https://api.openai.com/v1/chat/completions"),
            "https://api.openai.com/v1",
        )
        self.assertEqual(normalize_openai_base_url(""), DEFAULT_OPENAI_BASE_URL)

    def test_apply_openai_preset(self) -> None:
        applied = apply_openai_preset("xai")
        self.assertEqual(applied["openai_preset"], "xai")
        self.assertIn("api.x.ai", applied["openai_base_url"])
        self.assertTrue(applied["openai_model"])
        gem = apply_openai_preset("gemini")
        self.assertEqual(gem["openai_model"], "gemini-3.1-flash-lite")

    def test_normalize_api_key(self) -> None:
        from btf_viewer_pkg.ai_assistant import normalize_api_key, openai_request_headers
        self.assertEqual(normalize_api_key("  Bearer AIzaSyAbc  "), "AIzaSyAbc")
        self.assertEqual(normalize_api_key('"AIzaSyAbc"'), "AIzaSyAbc")
        self.assertEqual(normalize_api_key("GEMINI_API_KEY"), "")
        # Smart quotes / CJK junk must not reach HTTP headers (web fetch).
        self.assertEqual(normalize_api_key("“AIzaSyAbc”"), "AIzaSyAbc")
        self.assertEqual(normalize_api_key("AIza密鑰SyAbc"), "AIzaSyAbc")
        headers = openai_request_headers(
            "AIzaSyAbc",
            base_url="https://generativelanguage.googleapis.com/v1beta/openai",
        )
        self.assertEqual(headers["Authorization"], "Bearer AIzaSyAbc")
        self.assertNotIn("x-goog-api-key", headers)

    def test_openai_http_429_tip(self) -> None:
        from btf_viewer_pkg.ai_assistant import _openai_http_error_tip
        tip = _openai_http_error_tip(
            429, "RESOURCE_EXHAUSTED",
            base_url="https://generativelanguage.googleapis.com/v1beta/openai",
        )
        self.assertIn("quota", tip.lower())
        self.assertIn("gemini-3.1-flash-lite", tip)

    def test_match_ollama_model(self) -> None:
        installed = ["qwen2.5:14b", "deepseek-r1:14b", "llama3.2:latest"]
        self.assertEqual(match_ollama_model("qwen2.5:14b", installed), "qwen2.5:14b")
        self.assertEqual(match_ollama_model("qwen2.5", installed), "qwen2.5:14b")
        self.assertIsNone(match_ollama_model("missing", installed))

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

    def test_system_prompt_language(self) -> None:
        en = build_ai_system_prompt("English")
        self.assertIn("Always write your entire reply in English.", en)
        zh = build_ai_system_prompt("Traditional Chinese (繁體中文)")
        self.assertIn("Traditional Chinese (繁體中文)", zh)


if __name__ == "__main__":
    unittest.main()
