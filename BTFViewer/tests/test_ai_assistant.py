"""AI assistant helpers (no Ollama network required)."""
from __future__ import annotations

import json
import os
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

from btf_viewer_pkg.ai_assistant import (  # noqa: E402
    AI_AUTH_API_KEY,
    AI_AUTH_BROWSER,
    AI_AUTH_NONE,
    AI_PRESET_CUSTOM,
    AI_PRESET_GEMINI,
    AI_PRESET_OLLAMA,
    AI_PRESET_OPENAI,
    AI_CHAT_TIMEOUT_S,
    AI_TEMPLATE_QUESTIONS,
    DEFAULT_AI_BASE_URL,
    DEFAULT_AI_PRESET,
    _ai_log_document_html,
    _format_ai_log_html,
    ai_chat_completion,
    apply_ai_preset,
    build_ai_system_prompt,
    build_ai_user_message,
    ai_jump_annotation_note,
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
    strip_ai_settings_jsonc,
    resolve_ai_settings,
)
from btf_viewer_pkg.ai_tools import (  # noqa: E402
    GEMINI_SKIP_THOUGHT_SIGNATURE,
    ai_viewer_tools,
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
        self.assertEqual(AI_TEMPLATE_QUESTIONS[2][1], "Triage findings")
        self.assertNotIn("tooldemo", ids)

    def test_templates_match_web_ollama_client(self) -> None:
        """Keep AI_TEMPLATE_QUESTIONS in sync with web/src/utils/ollamaClient.js."""
        import re

        js = (BTF_ROOT / "web/src/utils/ollamaClient.js").read_text(encoding="utf-8")
        start = js.index("export const AI_TEMPLATE_QUESTIONS = [")
        chunk = js[start:]
        web = []
        for m in re.finditer(
            r"id:\s*(?:'([^']+)'|AI_COMPARE_TEMPLATE_ID)\s*,\s*label:\s*'([^']+)'\s*,\s*"
            r"prompt:\s*((?:'[^']*'\s*\+\s*)*'[^']*')",
            chunk,
        ):
            tid = m.group(1) or "compare"
            label, expr = m.group(2), m.group(3)
            prompt = "".join(re.findall(r"'([^']*)'", expr))
            web.append((tid, label, prompt))
            if tid == "deadlines":
                break
        self.assertEqual(list(AI_TEMPLATE_QUESTIONS), web)

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
        self.assertEqual(active["auth_mode"], AI_AUTH_API_KEY)
        other = resolve_ai_settings(cfg, AI_PRESET_OLLAMA)
        self.assertEqual(other["model"], "llama3.2:3b")
        self.assertEqual(other["api_key"], "")
        self.assertEqual(other["auth_mode"], AI_AUTH_NONE)

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
            "gemini.json": (AI_PRESET_GEMINI, "api_key"),
            "openai.json": (AI_PRESET_OPENAI, "api_key"),
            "ollama.json": (AI_PRESET_OLLAMA, "none"),
            "deepseek.json": (AI_PRESET_CUSTOM, "api_key"),
            "grok.json": (AI_PRESET_CUSTOM, "api_key"),
        }
        for name, (preset, auth) in expected.items():
            path = os.path.join(here, "examples", "ai", name)
            with open(path, encoding="utf-8") as fh:
                text = fh.read()
            patch = parse_ai_settings_json(text)
            self.assertEqual(patch["preset"], preset, name)
            self.assertTrue(patch[f"{preset}_base_url"], name)
            self.assertTrue(patch[f"{preset}_model"], name)
            self.assertEqual(patch[f"{preset}_auth_mode"], auth, name)
            self.assertIn("// auth_mode:", text, name)
        multi_path = os.path.join(here, "examples", "ai", "presets.json")
        with open(multi_path, encoding="utf-8") as fh:
            multi_text = fh.read()
        self.assertIn("// auth_mode:", multi_text)
        multi = parse_ai_settings_json(multi_text)
        self.assertEqual(multi["preset"], AI_PRESET_OLLAMA)
        self.assertEqual(multi["ollama_auth_mode"], "none")
        self.assertEqual(multi["gemini_auth_mode"], "api_key")
        self.assertTrue(multi["openai_model"])
        self.assertTrue(multi["custom_base_url"])

    def test_ai_chat_requires_key_for_remote(self) -> None:
        from unittest.mock import patch

        from btf_viewer_pkg.ai_assistant import ai_chat

        env = {
            "OPENAI_API_KEY": "",
            "GEMINI_API_KEY": "",
            "OLLAMA_API_KEY": "",
        }
        with patch.dict(os.environ, env, clear=False):
            with self.assertRaises(RuntimeError) as ctx:
                ai_chat("hi", base_url="https://api.openai.com/v1", api_key="")
        self.assertIn("API key required", str(ctx.exception))

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

    def test_normalize_ai_auth_mode_and_status(self) -> None:
        from btf_viewer_pkg.ai_assistant import (
            ai_auth_status,
            ai_preset_signin_label,
            ai_preset_signin_url,
            default_ai_auth_mode,
            normalize_ai_auth_mode,
        )
        self.assertEqual(default_ai_auth_mode(AI_PRESET_OLLAMA), AI_AUTH_NONE)
        self.assertEqual(default_ai_auth_mode(AI_PRESET_GEMINI), AI_AUTH_API_KEY)
        self.assertEqual(normalize_ai_auth_mode("sign-in"), AI_AUTH_BROWSER)
        self.assertEqual(normalize_ai_auth_mode("oauth"), AI_AUTH_BROWSER)
        self.assertEqual(
            normalize_ai_auth_mode("", preset_id=AI_PRESET_OLLAMA), AI_AUTH_NONE)
        st = ai_auth_status(
            auth_mode=AI_AUTH_API_KEY, api_key="", preset_id=AI_PRESET_GEMINI,
            base_url="https://generativelanguage.googleapis.com/v1beta/openai")
        self.assertTrue(st["needs_auth"])
        self.assertEqual(st["label"], "Needs API key")
        signed = ai_auth_status(
            auth_mode=AI_AUTH_BROWSER, api_key="tok", preset_id=AI_PRESET_GEMINI)
        self.assertTrue(signed["signed_in"])
        self.assertIn("aistudio.google.com", ai_preset_signin_url(AI_PRESET_GEMINI))
        self.assertIn("Google", ai_preset_signin_label(AI_PRESET_GEMINI))

    def test_parse_ai_settings_json_auth_mode(self) -> None:
        patch = parse_ai_settings_json({
            "preset": "gemini",
            "base_url": "https://generativelanguage.googleapis.com/v1beta/openai",
            "authMode": "sign_in",
        })
        self.assertEqual(patch["gemini_auth_mode"], AI_AUTH_BROWSER)

    def test_parse_ai_settings_json_strips_line_comments(self) -> None:
        src = (
            '{\n'
            '  // auth_mode: none = local (no key); api_key = paste a provider key\n'
            '  "preset": "gemini",\n'
            '  "base_url": "https://generativelanguage.googleapis.com/v1beta/openai",\n'
            '  "auth_mode": "api_key"\n'
            '}\n'
        )
        self.assertIn("// auth_mode:", src)
        stripped = strip_ai_settings_jsonc(src)
        self.assertNotIn("// auth_mode:", stripped)
        self.assertIn("https://", stripped)
        patch = parse_ai_settings_json(src)
        self.assertEqual(patch["gemini_auth_mode"], AI_AUTH_API_KEY)

    def test_parse_ai_tls_verify(self) -> None:
        import ssl
        from unittest.mock import patch

        from btf_viewer_pkg.ai_assistant import (
            _ai_ssl_error_tip,
            ai_ssl_context,
            ai_urlopen,
            format_ai_tls_verify,
            parse_ai_settings_json,
            parse_ai_tls_verify,
            resolve_ai_settings,
        )

        self.assertTrue(parse_ai_tls_verify(""))
        self.assertFalse(parse_ai_tls_verify("false"))
        self.assertFalse(parse_ai_tls_verify(False))
        self.assertEqual(format_ai_tls_verify(False), "false")
        self.assertEqual(resolve_ai_settings({})["tls_verify"], "true")
        self.assertEqual(
            resolve_ai_settings({"custom_tls_verify": "false"}, "custom")["tls_verify"],
            "false",
        )
        patch_json = parse_ai_settings_json({
            "preset": "custom",
            "base_url": "https://gateway.internal/v1",
            "tls_verify": False,
        })
        self.assertEqual(patch_json["custom_tls_verify"], "false")
        insecure = parse_ai_settings_json({
            "preset": "custom",
            "base_url": "https://gateway.internal/v1",
            "insecure_tls": True,
        })
        self.assertEqual(insecure["custom_tls_verify"], "false")
        self.assertIsNone(ai_ssl_context(True))
        ctx = ai_ssl_context(False)
        self.assertEqual(ctx.verify_mode, ssl.CERT_NONE)
        self.assertFalse(ctx.check_hostname)
        captured: dict = {}

        def _urlopen(req, timeout=None, context=None):  # noqa: ANN001
            captured["timeout"] = timeout
            captured["context"] = context
            return object()

        with patch("btf_viewer_pkg.ai_assistant.urllib.request.urlopen", _urlopen):
            ai_urlopen("req", 5.0, tls_verify=False)
            self.assertEqual(captured["timeout"], 5.0)
            self.assertEqual(captured["context"].verify_mode, ssl.CERT_NONE)
            ai_urlopen("req", 3.0, tls_verify=True)
            self.assertIsNone(captured["context"])
        tip = _ai_ssl_error_tip(
            OSError("CERTIFICATE_VERIFY_FAILED self-signed certificate"),
            tls_verify=True,
        )
        self.assertIn("Allow self-signed TLS", tip)

    def test_timeout_tip_explains_models_vs_chat(self) -> None:
        from btf_viewer_pkg.ai_assistant import (
            _ai_is_timeout_error,
            _ai_timeout_error_tip,
        )

        err = TimeoutError("The read operation timed out")
        self.assertTrue(_ai_is_timeout_error(err))
        tip = _ai_timeout_error_tip(err, timeout_s=120)
        self.assertIn("120s", tip)
        self.assertIn("GET /models", tip)
        self.assertIn("curl", tip)
        self.assertIn("stream", tip)

    def test_http_401_tip_mentions_sign_in(self) -> None:
        from btf_viewer_pkg.ai_assistant import _ai_http_error_tip
        tip = _ai_http_error_tip(401, "unauthorized")
        self.assertIn("Sign in", tip)
        self.assertIn("API key", tip)

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

    def test_ai_jump_annotation_note(self) -> None:
        self.assertEqual(ai_jump_annotation_note(1386000), "AI jump:1386000")
        self.assertEqual(ai_jump_annotation_note(1386000.0), "AI jump:1386000")
        self.assertEqual(ai_jump_annotation_note(99.5), "AI jump:99.5")

    def test_format_ai_log_html_links(self) -> None:
        html_out = _format_ai_log_html("assistant", "Open jump:1805120 next")
        self.assertIn('href="btfjump:time/1805120"', html_out)
        self.assertIn(">jump:1805120</a>", html_out)
        self.assertIn("Assistant", html_out)
        self.assertIn('class="ai-turn"', html_out)
        # User text is escaped (no raw tags).
        esc = _format_ai_log_html("user", "<script>x</script>")
        self.assertIn("&lt;script&gt;", esc)
        self.assertNotIn("<script>", esc)
        self.assertIn("You", esc)

    def test_format_ai_log_html_separates_turns(self) -> None:
        """Each turn is its own table so a new prompt cannot glue onto the last reply."""
        user = _format_ai_log_html("user", "What is wrong?")
        asst = _format_ai_log_html("assistant", "Nothing much.")
        self.assertIn("ai-bubble", user)
        self.assertIn("ai-bubble", asst)
        self.assertIn("You", user)
        self.assertNotIn("Assistant", user)
        self.assertIn("Assistant", asst)
        doc = _ai_log_document_html([
            ("user", "Prompt one"),
            ("assistant", "Reply one"),
            ("user", "Prompt two"),
        ])
        self.assertEqual(doc.count('class="ai-turn"'), 3)
        self.assertEqual(doc.count('class="ai-turn-sep"'), 2)
        self.assertIn("Prompt two", doc)
        self.assertLess(doc.index("Reply one"), doc.index("Prompt two"))

    def test_tool_card_apply_href_avoids_extra_colon(self) -> None:
        html_out = _format_ai_log_html(
            "assistant",
            "Placing cursors.",
            [{"name": "set_cursors", "arguments": {"timestamps": [1, 2]}, "status": "pending"}],
            "b1",
        )
        self.assertIn('href="btfaction:apply/b1"', html_out)
        self.assertNotIn("btfaction:apply:b1", html_out)

    def test_chat_completion_sends_tools_and_parses_btftool(self) -> None:
        captured: list = []

        class _FakeResp:
            def __init__(self, body: bytes) -> None:
                self._body = body

            def read(self, n: int = -1) -> bytes:
                if not self._body:
                    return b""
                if n is None or n < 0:
                    out, self._body = self._body, b""
                    return out
                out, self._body = self._body[:n], self._body[n:]
                return out

            def close(self) -> None:
                return None

        def _urlopen(req, timeout=None, **_kw):  # noqa: ANN001
            captured.append(json.loads(req.data.decode("utf-8")))
            payload = {
                "choices": [{
                    "message": {
                        "role": "assistant",
                        "content": (
                            "Placing cursors.\n"
                            "```btftool\n"
                            '{"name": "set_cursors", "arguments": {"timestamps": [10, 20]}}\n'
                            "```\n"
                        ),
                    },
                }],
            }
            return _FakeResp(json.dumps(payload).encode("utf-8"))

        with patch("btf_viewer_pkg.ai_assistant.urllib.request.urlopen", _urlopen):
            turn = ai_chat_completion(
                query="put cursors at 10 and 20",
                tools=ai_viewer_tools(),
                base_url="http://127.0.0.1:11434/v1",
                model="phi4-mini:3.8b",
            )
        self.assertEqual(len(captured), 1)
        self.assertIn("tools", captured[0])
        self.assertNotIn("tool_choice", captured[0])
        self.assertEqual(turn["tool_calls"][0]["name"], "set_cursors")
        self.assertEqual(turn["tool_calls"][0]["arguments"]["timestamps"], [10.0, 20.0])
        self.assertNotIn("btftool", turn["content"])

    def test_chat_completion_keeps_tools_on_generic_400(self) -> None:
        import io
        import urllib.error

        def _urlopen(req, timeout=None, **_kw):  # noqa: ANN001
            raise urllib.error.HTTPError(
                "http://127.0.0.1:11434/v1/chat/completions",
                400,
                "Bad Request",
                hdrs=None,
                fp=io.BytesIO(b'{"error":"unknown model foo"}'),
            )

        with patch("btf_viewer_pkg.ai_assistant.urllib.request.urlopen", _urlopen):
            with self.assertRaises(RuntimeError) as ctx:
                ai_chat_completion(
                    query="hi",
                    tools=ai_viewer_tools(),
                    base_url="http://127.0.0.1:11434/v1",
                    model="missing",
                )
        self.assertIn("HTTP 400", str(ctx.exception))
        self.assertNotIn("does not support tools", str(ctx.exception).lower())

    def test_chat_completion_fills_gemini_tool_result_names(self) -> None:
        captured = []

        class _FakeResp:
            def __init__(self, body: bytes) -> None:
                self._body = body

            def read(self, n: int = -1) -> bytes:
                if not self._body:
                    return b""
                if n is None or n < 0:
                    out, self._body = self._body, b""
                    return out
                out, self._body = self._body[:n], self._body[n:]
                return out

            def close(self) -> None:
                return None

        def _urlopen(req, timeout=None, **_kw):  # noqa: ANN001, ARG001
            captured.append(json.loads(req.data.decode("utf-8")))
            return _FakeResp(
                b'{"choices":[{"message":{"role":"assistant","content":"ok"}}]}'
            )

        messages = [
            {"role": "user", "content": "fix inversion"},
            {
                "role": "assistant",
                "content": "Applying.",
                "tool_calls": [
                    {
                        "id": "c1",
                        "type": "function",
                        "function": {
                            "name": "set_cursors",
                            "arguments": '{"timestamps":[1,2]}',
                        },
                    },
                    {
                        "id": "c2",
                        "type": "function",
                        "function": {
                            "name": "highlight_task",
                            "arguments": '{"task_name_or_id":"PS[228]"}',
                        },
                    },
                ],
            },
            {"role": "tool", "tool_call_id": "c1", "content": '{"ok":true}'},
            {"role": "tool", "tool_call_id": "c2", "content": '{"ok":true}'},
        ]
        with patch("btf_viewer_pkg.ai_assistant.urllib.request.urlopen", _urlopen):
            ai_chat_completion(
                query="",
                messages=messages,
                tools=ai_viewer_tools(),
                base_url="http://127.0.0.1:11434/v1",
                model="gemini-2.5-flash",
            )
        sent = captured[0]["messages"]
        tools = [m for m in sent if m.get("role") == "tool"]
        self.assertEqual(
            [m.get("name") for m in tools],
            ["set_cursors", "highlight_task"],
        )
        asst = next(m for m in sent if m.get("role") == "assistant")
        self.assertNotIn("extra_content", (asst.get("tool_calls") or [{}])[0])

    def test_chat_completion_echoes_gemini_thought_signatures(self) -> None:
        captured = []

        class _FakeResp:
            def __init__(self, body: bytes) -> None:
                self._body = body

            def read(self, n: int = -1) -> bytes:
                if not self._body:
                    return b""
                if n is None or n < 0:
                    out, self._body = self._body, b""
                    return out
                out, self._body = self._body[:n], self._body[n:]
                return out

            def close(self) -> None:
                return None

        def _urlopen(req, timeout=None, **_kw):  # noqa: ANN001, ARG001
            captured.append(json.loads(req.data.decode("utf-8")))
            return _FakeResp(
                b'{"choices":[{"message":{"role":"assistant","content":"ok"}}]}'
            )

        sig = "CvcQAdHtimRealSignature=="
        messages = [
            {"role": "user", "content": "Highest latency"},
            {
                "role": "assistant",
                "content": "Applying.",
                "tool_calls": [
                    {
                        "id": "c1",
                        "type": "function",
                        "function": {
                            "name": "zoom_to_range",
                            "arguments": '{"start_time":1,"end_time":2}',
                        },
                        "extra_content": {
                            "google": {"thought_signature": sig},
                        },
                    },
                    {
                        "id": "c2",
                        "type": "function",
                        "function": {
                            "name": "highlight_task",
                            "arguments": '{"task_name_or_id":"PS[228]"}',
                        },
                    },
                ],
            },
            {"role": "tool", "tool_call_id": "c1", "name": "zoom_to_range",
             "content": '{"ok":true}'},
            {"role": "tool", "tool_call_id": "c2", "name": "highlight_task",
             "content": '{"ok":true}'},
        ]
        with patch("btf_viewer_pkg.ai_assistant.urllib.request.urlopen", _urlopen):
            ai_chat_completion(
                query="",
                messages=messages,
                tools=ai_viewer_tools(),
                base_url="https://generativelanguage.googleapis.com/v1beta/openai",
                model="gemini-flash-lite-latest",
                preset="gemini",
                api_key="test-key",
            )
        asst = next(
            m for m in captured[0]["messages"] if m.get("role") == "assistant")
        calls = asst["tool_calls"]
        self.assertEqual(
            calls[0]["extra_content"]["google"]["thought_signature"], sig)
        self.assertNotIn("extra_content", calls[1])

        captured.clear()
        nameless = [
            {"role": "user", "content": "Highest latency"},
            {
                "role": "assistant",
                "content": "Applying.",
                "tool_calls": [{
                    "id": "c1",
                    "type": "function",
                    "function": {
                        "name": "highlight_task",
                        "arguments": '{"task_name_or_id":"PS[228]"}',
                    },
                }],
            },
            {"role": "tool", "tool_call_id": "c1", "name": "highlight_task",
             "content": '{"ok":true}'},
        ]
        with patch("btf_viewer_pkg.ai_assistant.urllib.request.urlopen", _urlopen):
            ai_chat_completion(
                query="",
                messages=nameless,
                tools=ai_viewer_tools(),
                base_url="https://generativelanguage.googleapis.com/v1beta/openai",
                model="gemini-flash-lite-latest",
                preset="gemini",
                api_key="test-key",
            )
        asst = next(
            m for m in captured[0]["messages"] if m.get("role") == "assistant")
        self.assertEqual(
            asst["tool_calls"][0]["extra_content"]["google"]["thought_signature"],
            GEMINI_SKIP_THOUGHT_SIGNATURE,
        )

    def test_chat_completion_default_timeout(self) -> None:
        self.assertEqual(AI_CHAT_TIMEOUT_S, 120.0)
        captured = []

        def _urlopen(req, timeout=None, **_kw):  # noqa: ANN001
            captured.append(timeout)
            raise TimeoutError("slow")

        with patch("btf_viewer_pkg.ai_assistant.urllib.request.urlopen", _urlopen):
            with self.assertRaises(RuntimeError) as ctx:
                ai_chat_completion(
                    query="hi",
                    base_url="http://127.0.0.1:11434/v1",
                    model="phi4-mini:3.8b",
                )
        self.assertEqual(captured, [AI_CHAT_TIMEOUT_S])
        self.assertIn("timed out", str(ctx.exception).lower())

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
        self.assertIn('href="btfjump:time/42"', html_out)
        self.assertIn("<ul>", html_out)
        self.assertIn("&lt;tag&gt;", html_out)
        self.assertNotIn("<tag>", html_out)
        # Unsafe raw HTML is escaped.
        unsafe = markdown_to_safe_html("<script>alert(1)</script>")
        self.assertIn("&lt;script&gt;", unsafe)
        self.assertNotIn("<script>", unsafe)

        # Interrupted 1./2./3. runs must keep source numbers (not restart at 1).
        numbered = markdown_to_safe_html(
            "1. **First issue**\n\n"
            "Details about thrashing.\n\n"
            "- **Open:** Migration Heatmap\n\n"
            "2. **Second issue**\n\n"
            "Priority inversion risk.\n\n"
            "3. **Third issue**\n"
        )
        self.assertIn("<ol><li><strong>First issue</strong></li></ol>", numbered)
        self.assertIn(
            '<ol start="2"><li><strong>Second issue</strong></li></ol>',
            numbered,
        )
        self.assertIn(
            '<ol start="3"><li><strong>Third issue</strong></li></ol>',
            numbered,
        )
        self.assertIn(
            "<ul><li><strong>Open:</strong> Migration Heatmap</li></ul>",
            numbered,
        )

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
        self.assertIn('href="btfjump:time/1805000"', doc)
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
