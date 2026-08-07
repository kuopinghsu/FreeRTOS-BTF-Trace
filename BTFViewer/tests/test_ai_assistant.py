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
    AI_TEMPLATE_QUESTIONS,
    _format_ai_log_html,
    build_ai_system_prompt,
    build_ai_user_message,
    extract_jump_times,
    match_ollama_model,
    normalize_ollama_url,
)


class AiAssistantHelpersTests(unittest.TestCase):
    def test_templates_nonempty(self) -> None:
        self.assertGreaterEqual(len(AI_TEMPLATE_QUESTIONS), 5)
        ids = [t[0] for t in AI_TEMPLATE_QUESTIONS]
        self.assertEqual(ids[0], "findings")
        self.assertEqual(AI_TEMPLATE_QUESTIONS[0][1], "Analysis Findings")
        self.assertIn("triage", ids)
        self.assertIn("migrations", ids)

    def test_normalize_url(self) -> None:
        self.assertEqual(normalize_ollama_url("http://localhost:11434/"), "http://localhost:11434")
        self.assertEqual(normalize_ollama_url(""), "http://localhost:11434")

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

    def test_system_prompt_language(self) -> None:
        en = build_ai_system_prompt("English")
        self.assertIn("Always write your entire reply in English.", en)
        zh = build_ai_system_prompt("Traditional Chinese (繁體中文)")
        self.assertIn("Traditional Chinese (繁體中文)", zh)


if __name__ == "__main__":
    unittest.main()
