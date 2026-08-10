"""Diagnostic assistant for BTF Viewer (any OpenAI-compatible endpoint).

Sends structured Analysis Findings (and optional scoped metrics) to a chat
endpoint — never the raw BTF event stream.
"""
from __future__ import annotations

import json
import os
import re
import ssl
import threading
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

from ._imports import *  # noqa: F403,F401
from .config import rasterize_svg_pixmap
from .ai_mermaid import (
    _link_row_html,
    decode_mermaid_zoom_token,
    hit_test_mermaid,
    mermaid_block_html,
    mermaid_to_svg,
)
from .ai_tools import (
    AI_TOOL_SYSTEM_ADDENDUM,
    ai_viewer_tools,
    btf_jump_href,
    build_ai_report_csv,
    build_ai_report_html,
    canonical_assistant_tool_message,
    ensure_gemini_thought_signatures,
    extract_tool_calls,
    format_tool_result_content,
    is_export_tool,
    max_tool_rounds,
    merge_tool_calls,
    message_content_text,
    needs_gemini_thought_signatures,
    normalize_tool_chat_messages,
    parse_ai_auto_apply,
    parse_btf_highlight_href,
    parse_btf_jump_href,
    parse_tool_calls_from_text,
    strip_parsed_tool_markup,
    summarise_tool_call,
    tool_batch_auto_runs,
    tool_result_message,
    tool_result_payload,
    validate_tool_call,
)


class OllamaCancelled(Exception):
    """User stopped an in-flight AI request."""


class _MermaidZoomDialog(QDialog):
    """Larger view of an AI mermaid diagram (scroll to zoom)."""

    def __init__(
        self,
        source: str,
        parent=None,
        *,
        on_link: Optional[Callable[[QUrl], None]] = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Diagram")
        self.setModal(True)
        self._source = source or ""
        self._svg = mermaid_to_svg(self._source, interactive=False)
        self._scale = 2.0
        self._hit_scale = 2.0
        lay = QVBoxLayout(self)
        hint = QLabel(
            "Scroll to zoom. Click a task/core in the figure or a name below."
        )
        hint.setStyleSheet("color:#8b98a8;font-size:11px;")
        hint.setWordWrap(True)
        lay.addWidget(hint)
        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(False)
        self._scroll.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._img = QLabel()
        self._img.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._img.setCursor(Qt.CursorShape.PointingHandCursor)
        self._on_link = on_link
        self._scroll.setWidget(self._img)
        self._scroll.viewport().installEventFilter(self)
        self._img.installEventFilter(self)
        lay.addWidget(self._scroll, 1)
        links_html = _link_row_html(self._source)
        if links_html:
            links = QTextBrowser()
            links.setOpenExternalLinks(False)
            links.setOpenLinks(False)
            links.setMaximumHeight(80)
            links.setHtml(
                f"<html><body style=\"background:#12161d;color:#dbe2ea;\">"
                f"{links_html}</body></html>"
            )
            if on_link:
                links.anchorClicked.connect(on_link)
            lay.addWidget(links)
        close = QPushButton("Close")
        close.clicked.connect(self.accept)
        lay.addWidget(close, 0, Qt.AlignmentFlag.AlignRight)
        self._render()
        pm = self._img.pixmap()
        pw = pm.width() if pm and not pm.isNull() else 480
        ph = pm.height() if pm and not pm.isNull() else 280
        self.resize(min(960, max(480, pw + 48)), min(720, max(360, ph + 160)))

    def eventFilter(self, obj, event):  # noqa: N802
        if obj is self._scroll.viewport() and event.type() == QEvent.Type.Wheel:
            delta = event.angleDelta().y()
            if delta:
                factor = 1.15 if delta > 0 else 1.0 / 1.15
                self._scale = max(0.5, min(6.0, self._scale * factor))
                self._render()
                return True
        if obj is self._img and event.type() == QEvent.Type.MouseButtonPress:
            if event.button() == Qt.MouseButton.LeftButton and self._on_link:
                pos = event.position().toPoint() if hasattr(event, "position") else event.pos()
                hit = hit_test_mermaid(
                    self._source, pos.x(), pos.y(), scale=self._hit_scale)
                if hit:
                    _kind, value = hit
                    self._on_link(QUrl(f"btfhighlight:{urllib.parse.quote(value, safe='')}"))
                    return True
        return QDialog.eventFilter(self, obj, event)

    def _render(self) -> None:
        if not self._svg:
            self._img.setText("Could not render diagram.")
            return
        pm, hit_scale = rasterize_svg_pixmap(
            self._svg, scale=self._scale, fill=QColor("#12161d"))
        if pm.isNull():
            self._img.setText("Could not render diagram.")
            return
        self._hit_scale = hit_scale
        self._img.setPixmap(pm)
        self._img.resize(pm.size())



# Alias used by newer call sites; same exception.
AiCancelled = OllamaCancelled
AI_SYSTEM_PROMPT = (
    "You are an expert Real-Time Operating System (RTOS) and SMP trace analysis "
    "assistant for FreeRTOS BTF traces. Analyse the provided structured metrics "
    "and answer the user's diagnostic question clearly. Focus on root causes "
    "(preemption, priority inversion, lock contention, core thrashing, switch "
    "overhead, tick health). Prefer concrete task names, cores, and durations. "
    "When mentioning a time, write it as jump:TIME where TIME is the numeric "
    "value in the trace time unit (e.g. jump:1805120). Keep answers concise. "
    + AI_TOOL_SYSTEM_ADDENDUM
)

# Preferred reply language (Settings → AI / Language… dialog). Keep in sync with web.
DEFAULT_AI_RESPONSE_LANGUAGE = "English"
AI_RESPONSE_LANGUAGES: Tuple[str, ...] = (
    "English",
    "Traditional Chinese (繁體中文)",
    "Simplified Chinese (简体中文)",
    "Japanese (日本語)",
    "Korean (한국어)",
    "German",
    "French",
    "Spanish",
    "Klingon (tlhIngan Hol)",
)


def build_ai_system_prompt(
    response_language: str = DEFAULT_AI_RESPONSE_LANGUAGE,
) -> str:
    """System prompt with an explicit reply-language instruction."""
    lang = (response_language or DEFAULT_AI_RESPONSE_LANGUAGE).strip() or DEFAULT_AI_RESPONSE_LANGUAGE
    return (
        f"{AI_SYSTEM_PROMPT} Always write your entire reply in {lang}."
    )

# (id, label, prompt) — keep in sync with web/src/utils/ollamaClient.js
AI_COMPARE_TEMPLATE_ID = "compare"

AI_TEMPLATE_QUESTIONS: Tuple[Tuple[str, str, str], ...] = (
    (
        "findings",
        "Analysis Findings",
        "Walk through the Analysis Findings in the context. For each finding, "
        "state its severity, what it means for this RTOS/SMP system, and which "
        "Statistics section or timeline check to open next. If there are no "
        "findings, say so and suggest a default top-down inspection order.",
    ),
    (
        AI_COMPARE_TEMPLATE_ID,
        "Trace Compare",
        "Compare Trace A vs Trace B using the Trace Compare tables in the "
        "context. Highlight the largest deltas (CPU, migrations, latency, "
        "tick health, sync). Say which side is worse for each concern and "
        "which Statistics section or Trace Compare page to open next.",
    ),
    (
        "triage",
        "Triage findings",
        "Summarise the Analysis Findings and list the top three issues to "
        "investigate first, with the Statistics section to open for each.",
    ),
    (
        "latency",
        "Highest latency",
        "Which tasks show the highest latency or blocking? Explain likely "
        "causes using preemption, dispatch latency, and mutex evidence in "
        "the context.",
    ),
    (
        "wcet",
        "WCET / hot CPU",
        "Which tasks dominate CPU and which have the worst execution-slice "
        "Max? Recommend whether to affinity-pin, reduce fan-out, or inspect "
        "preemption.",
    ),
    (
        "migrations",
        "Migration thrash",
        "Is there core thrashing or lock-bounce? Cite migration rate, ping, "
        "dwell, and any hot mutex/queue bounces. Suggest affinity or "
        "ownership fixes.",
    ),
    (
        "balance",
        "Core balance",
        "Is SMP load balance healthy? Interpret Load Balance Score / σ and "
        "whether Concurrent Core Active or Switch Overhead needs attention.",
    ),
    (
        "tick",
        "Tick health",
        "Interpret Trace Health (TICK). Are large gaps expected under "
        "tickless idle, or should we re-check inside a busy cursor window?",
    ),
    (
        "priority",
        "Priority inversion",
        "Is there priority inversion or L/M/H geometry? Explain any inherit "
        "episodes and what to verify next.",
    ),
    (
        "deadlines",
        "Deadline / budget",
        "Are there deadline or CPU-budget concerns in the findings? What "
        "should the engineer measure next?",
    ),
)

# Every provider is reached over its OpenAI-compatible /chat/completions API,
# including Ollama (http://localhost:11434/v1).
AI_PRESET_CUSTOM = "custom"
AI_PRESET_OLLAMA = "ollama"
AI_PRESET_OPENAI = "openai"
AI_PRESET_GEMINI = "gemini"

# (id, label, base_url, model)
AI_PRESETS: Tuple[Tuple[str, str, str, str], ...] = (
    (AI_PRESET_CUSTOM, "Custom", "", ""),
    (AI_PRESET_OLLAMA, "Ollama", "http://localhost:11434/v1", "phi4-mini:3.8b"),
    (AI_PRESET_OPENAI, "OpenAI", "https://api.openai.com/v1", "gpt-4o-mini"),
    (
        AI_PRESET_GEMINI,
        "Google Gemini",
        "https://generativelanguage.googleapis.com/v1beta/openai",
        # Rolling alias: concrete versions come and go per account/tier.
        "gemini-flash-lite-latest",
    ),
)

DEFAULT_AI_PRESET = AI_PRESET_OLLAMA
DEFAULT_AI_BASE_URL = "http://localhost:11434/v1"
DEFAULT_AI_MODEL = "phi4-mini:3.8b"
# Keep in sync with web/src/utils/ollamaClient.js (ms equivalents).
AI_CHAT_TIMEOUT_S = 120.0
AI_LIST_MODELS_TIMEOUT_S = 12.0
AI_TEST_TIMEOUT_S = 120.0

# Per-preset settings stored in btf_viewer.rc / browser storage.
AI_PRESET_FIELDS: Tuple[str, ...] = (
    "base_url", "model", "api_key", "auth_mode", "tls_verify",
)

AI_AUTH_NONE = "none"
AI_AUTH_API_KEY = "api_key"
AI_AUTH_BROWSER = "browser"
AI_AUTH_MODES: Tuple[str, ...] = (AI_AUTH_NONE, AI_AUTH_API_KEY, AI_AUTH_BROWSER)
AI_AUTH_MODE_LABELS: Tuple[Tuple[str, str], ...] = (
    (AI_AUTH_NONE, "None (local)"),
    (AI_AUTH_API_KEY, "API key"),
    (AI_AUTH_BROWSER, "Sign in"),
)

# Hosts that serve a local model and therefore need no API key.
# Keep in sync with LOCAL_AI_HOSTS in web/src/utils/ollamaClient.js.
LOCAL_AI_HOSTS: Tuple[str, ...] = (
    "localhost",
    "127.0.0.1",
    "0.0.0.0",
    "::1",
    "host.docker.internal",
)

# Where each vendor issues API keys (shown as a Settings hint).
AI_PRESET_KEY_URLS: Dict[str, str] = {
    AI_PRESET_OPENAI: "https://platform.openai.com/api-keys",
    AI_PRESET_GEMINI: "https://aistudio.google.com/apikey",
    AI_PRESET_OLLAMA: "https://ollama.com/settings/keys",
}

AI_PRESET_SIGNIN_LABELS: Dict[str, str] = {
    AI_PRESET_OPENAI: "Sign in with OpenAI…",
    AI_PRESET_GEMINI: "Sign in with Google…",
    AI_PRESET_OLLAMA: "Open Ollama sign-in…",
    AI_PRESET_CUSTOM: "Open provider sign-in…",
}


def normalize_ai_preset(preset_id: Optional[str]) -> str:
    """Map a stored/legacy preset id onto one of the known presets."""
    want = (preset_id or DEFAULT_AI_PRESET).strip().lower().replace("-", "_")
    for row in AI_PRESETS:
        if row[0] == want:
            return row[0]
    if want in ("google", "google_gemini", "gemini_openai"):
        return AI_PRESET_GEMINI
    if want in ("ollama_cloud", "local"):
        return AI_PRESET_OLLAMA
    if want in ("chatgpt", "open_ai"):
        return AI_PRESET_OPENAI
    return AI_PRESET_CUSTOM


def ai_preset_info(preset_id: str) -> Tuple[str, str, str, str]:
    """Return (id, label, base_url, model) for *preset_id*."""
    want = normalize_ai_preset(preset_id)
    for row in AI_PRESETS:
        if row[0] == want:
            return row
    return AI_PRESETS[0]


def apply_ai_preset(preset_id: str) -> Dict[str, str]:
    """Base URL / model to fill in when the user picks a preset."""
    _id, _label, base, model = ai_preset_info(preset_id)
    return {"preset": _id, "base_url": base, "model": model}


def ai_preset_setting_key(preset_id: str, field: str) -> str:
    """Settings key holding *field* for *preset_id* (e.g. ``ollama_base_url``)."""
    return f"{normalize_ai_preset(preset_id)}_{field}"


def resolve_ai_settings(
    cfg: Optional[Dict[str, Any]] = None,
    preset_id: Optional[str] = None,
) -> Dict[str, str]:
    """Active preset plus its stored base URL / model / API key.

    Values fall back to the preset defaults, so a never-edited preset still
    works. Pass *preset_id* to read a preset other than the selected one.
    """
    c = dict(cfg or {})
    preset = normalize_ai_preset(
        preset_id if preset_id is not None else c.get("preset"))
    _id, _label, def_base, def_model = ai_preset_info(preset)
    base_url = str(c.get(f"{preset}_base_url", "") or def_base)
    return {
        "preset": preset,
        "base_url": base_url,
        "model": str(c.get(f"{preset}_model", "") or def_model),
        "api_key": str(c.get(f"{preset}_api_key", "") or ""),
        "auth_mode": normalize_ai_auth_mode(
            c.get(f"{preset}_auth_mode", ""),
            preset_id=preset,
            base_url=base_url,
        ),
        "tls_verify": format_ai_tls_verify(c.get(f"{preset}_tls_verify", "")),
    }


def migrate_ai_settings(cfg: Optional[Dict[str, Any]] = None) -> Dict[str, str]:
    """Patch moving pre-preset settings onto the per-preset keys.

    Older builds stored one provider (``provider``) with separate ``ollama_*``
    and ``openai_*`` fields, where ``openai_*`` meant "the one OpenAI-compatible
    endpoint" and could point at any vendor. Those key names now belong to the
    OpenAI preset, so they are only read as legacy when a retired key
    (``provider``, ``openai_preset`` or ``ollama_url``) is still present, and
    they are cleared when their values belong to another preset.

    Returns only the keys that need writing; an empty dict means the settings
    are already in the current shape.
    """
    c = dict(cfg or {})
    patch: Dict[str, str] = {}
    provider = str(c.get("provider", "") or "").strip().lower().replace("-", "_")
    legacy_preset = str(c.get("openai_preset", "") or "").strip().lower()
    old_ollama_url = str(c.get("ollama_url", "") or "").strip()
    if not (provider or legacy_preset or old_ollama_url):
        return patch

    old_openai_url = str(c.get("openai_base_url", "") or "").strip()
    openai_target = _legacy_openai_target(legacy_preset, old_openai_url)

    def _keep(key: str, value: str) -> None:
        if value and not str(c.get(key, "") or "").strip():
            patch[key] = value

    if old_ollama_url:
        _keep("ollama_base_url", normalize_ai_base_url(old_ollama_url))
    _keep("ollama_model", str(c.get("ollama_model", "") or "").strip())
    _keep("ollama_api_key", str(c.get("ollama_api_key", "") or "").strip())

    old_openai_model = str(c.get("openai_model", "") or "").strip()
    old_openai_key = str(c.get("openai_api_key", "") or "").strip()
    if openai_target == AI_PRESET_OPENAI:
        # Same key names before and after; the stored values already fit.
        if old_openai_url:
            patch["openai_base_url"] = normalize_ai_base_url(old_openai_url)
    else:
        if old_openai_url:
            _keep(f"{openai_target}_base_url", normalize_ai_base_url(old_openai_url))
            patch["openai_base_url"] = ""
        _keep(f"{openai_target}_model", old_openai_model)
        _keep(f"{openai_target}_api_key", old_openai_key)
        if old_openai_model:
            patch["openai_model"] = ""
        if old_openai_key:
            patch["openai_api_key"] = ""

    if not str(c.get("preset", "") or "").strip():
        if provider and provider != "ollama":
            patch["preset"] = openai_target
        elif provider or old_ollama_url:
            patch["preset"] = AI_PRESET_OLLAMA
    return patch


def _legacy_openai_target(legacy_preset: str, legacy_base_url: str) -> str:
    """Preset that owns the retired ``openai_*`` fields."""
    want = legacy_preset.strip().lower().replace("-", "_")
    if want in ("gemini", "google", "google_gemini"):
        return AI_PRESET_GEMINI
    if want in ("openai", "chatgpt"):
        return AI_PRESET_OPENAI
    if want:
        return AI_PRESET_CUSTOM
    host = normalize_ai_base_url(legacy_base_url).lower()
    if "api.openai.com" in host:
        return AI_PRESET_OPENAI
    if "generativelanguage" in host:
        return AI_PRESET_GEMINI
    return AI_PRESET_CUSTOM


# Preset ids accepted by an import file beyond the current ones; older exports
# and vendor names map onto an existing preset.
AI_IMPORT_PRESET_ALIASES: Dict[str, str] = {
    "chatgpt": AI_PRESET_OPENAI,
    "open_ai": AI_PRESET_OPENAI,
    "openai_compatible": AI_PRESET_CUSTOM,
    "xai": AI_PRESET_CUSTOM,
    "grok": AI_PRESET_CUSTOM,
    "deepseek": AI_PRESET_CUSTOM,
    "google": AI_PRESET_GEMINI,
    "google_gemini": AI_PRESET_GEMINI,
}


def _ai_json_tls_verify(fields: Dict[str, Any]) -> Optional[str]:
    """Return ``true``/``false`` when the import file mentions TLS verify."""
    for name in ("tls_verify", "tlsVerify", "verify_tls", "verifyTls"):
        if name in fields:
            return format_ai_tls_verify(fields.get(name), default=True)
    for name in (
        "insecure_tls", "insecureTls", "tls_insecure", "allow_insecure_tls",
        "allowInsecureTls",
    ):
        if name in fields:
            insecure = parse_ai_tls_verify(fields.get(name), default=False)
            return "false" if insecure else "true"
    return None


def _ai_json_str(obj: Dict[str, Any], *names: str) -> str:
    for name in names:
        value = obj.get(name)
        if value is not None and not isinstance(value, (dict, list)):
            text = str(value).strip()
            if text:
                return text
    return ""


def _ai_import_preset_id(raw: str) -> str:
    """Preset id for an import file, rejecting names we cannot place."""
    want = raw.strip().lower().replace("-", "_").replace(" ", "_")
    for row in AI_PRESETS:
        if want in (row[0], row[1].lower().replace(" ", "_")):
            return row[0]
    if want in AI_IMPORT_PRESET_ALIASES:
        return AI_IMPORT_PRESET_ALIASES[want]
    valid = ", ".join(row[0] for row in AI_PRESETS)
    raise ValueError(f"Unknown preset {raw!r}. Use one of: {valid}.")


def _ai_import_preset_from_url(base_url: str) -> str:
    """Guess the preset when the file only carries a base URL."""
    host = normalize_ai_base_url(base_url).lower()
    if is_local_ai_host(host):
        return AI_PRESET_OLLAMA
    if "generativelanguage" in host or "gemini" in host:
        return AI_PRESET_GEMINI
    if "api.openai.com" in host:
        return AI_PRESET_OPENAI
    return AI_PRESET_CUSTOM


def strip_ai_settings_jsonc(text: str) -> str:
    """Drop whole-line ``//`` comments so example files can document ``auth_mode``.

    Only full-line comments are removed, so ``https://`` inside strings is safe.
    """
    lines = []
    for line in str(text or "").splitlines():
        if line.lstrip().startswith("//"):
            continue
        lines.append(line)
    return "\n".join(lines)


def parse_ai_settings_json(data: Any) -> Dict[str, str]:
    """Settings patch from an AI settings JSON file (see ``examples/ai``).

    Accepts a flat file describing one endpoint::

        {"preset": "gemini", "base_url": "…", "model": "…", "api_key": "",
         "auth_mode": "api_key"}

    or a ``presets`` object carrying several at once. snake_case and camelCase
    key names both work, so files exported from either app import into both.
    Whole-line ``//`` comments are ignored. Raises ``ValueError`` with a
    user-facing message when the file cannot be applied.
    """
    if isinstance(data, (bytes, bytearray)):
        data = data.decode("utf-8", errors="replace")
    if isinstance(data, str):
        try:
            data = json.loads(strip_ai_settings_jsonc(data))
        except ValueError as exc:
            raise ValueError(f"Not valid JSON: {exc}") from exc
    if not isinstance(data, dict):
        raise ValueError("AI settings file must contain a JSON object.")

    raw_preset = _ai_json_str(data, "preset", "aiPreset", "ai_preset", "provider")
    preset = _ai_import_preset_id(raw_preset) if raw_preset else ""

    per_preset: Dict[str, Dict[str, str]] = {}

    def _collect(target: str, fields: Dict[str, Any]) -> None:
        base_url = _ai_json_str(fields, "base_url", "baseUrl", "url")
        if base_url:
            if not base_url.lower().startswith(("http://", "https://")):
                raise ValueError(
                    f"Base URL must start with http:// or https:// (got {base_url!r})."
                )
            base_url = normalize_ai_base_url(base_url)
        entry = {
            "base_url": base_url,
            "model": _ai_json_str(fields, "model", "model_id", "modelId"),
            "api_key": normalize_api_key(
                _ai_json_str(fields, "api_key", "apiKey", "key")),
        }
        auth_raw = _ai_json_str(
            fields, "auth_mode", "authMode", "authentication")
        if auth_raw:
            entry["auth_mode"] = normalize_ai_auth_mode(
                auth_raw, preset_id=target, base_url=base_url)
        tls_s = _ai_json_tls_verify(fields)
        if tls_s is not None:
            entry["tls_verify"] = tls_s
        entry = {k: v for k, v in entry.items() if v or k == "tls_verify"}
        if entry:
            per_preset.setdefault(target, {}).update(entry)

    presets_obj = data.get("presets", data.get("aiPresets"))
    if presets_obj is not None:
        if not isinstance(presets_obj, dict):
            raise ValueError('"presets" must be an object keyed by preset id.')
        for key, fields in presets_obj.items():
            if not isinstance(fields, dict):
                raise ValueError(f'Preset {key!r} must be an object.')
            _collect(_ai_import_preset_id(str(key)), fields)

    flat_target = preset or _ai_import_preset_from_url(
        _ai_json_str(data, "base_url", "baseUrl", "url"))
    _collect(flat_target, data)
    if not preset and _ai_json_str(data, "base_url", "baseUrl", "url"):
        preset = flat_target
    if not preset and len(per_preset) == 1:
        preset = next(iter(per_preset))
    if not per_preset:
        raise ValueError(
            "No AI settings found. Expected base_url / model / api_key "
            "(optionally inside a presets object)."
        )

    _id, _label, def_base, _def_model = ai_preset_info(preset or DEFAULT_AI_PRESET)
    if preset and not def_base and not per_preset.get(preset, {}).get("base_url"):
        raise ValueError(f"Preset {preset!r} needs a base_url.")

    patch: Dict[str, str] = {}
    if preset:
        patch["preset"] = preset
    for target, fields in per_preset.items():
        for field, value in fields.items():
            patch[f"{target}_{field}"] = value
    language = _ai_json_str(
        data, "response_language", "responseLanguage", "aiResponseLanguage")
    if language:
        patch["response_language"] = language
    return patch


def normalize_api_key(api_key: Optional[str] = None) -> str:
    """Strip paste noise from an API key (quotes, Bearer prefix, non-ASCII junk).

    Browser ``fetch()`` rejects header values with non-ISO-8859-1 code points, so
    keep only printable ASCII (API keys are ASCII).
    """
    key = (api_key or "").strip()
    if not key:
        return ""
    # Zero-width / BOM / NBSP from rich-text paste.
    for ch in ("\ufeff", "\u200b", "\u200c", "\u200d", "\u00a0"):
        key = key.replace(ch, "")
    key = key.strip().strip("\"'").strip()
    # Unicode smart quotes / CJK punctuation often sneak in from paste.
    key = "".join(ch for ch in key if 0x20 <= ord(ch) <= 0x7E)
    key = key.strip().strip("\"'").strip()
    low = key.lower()
    if low.startswith("bearer "):
        key = key[7:].strip().strip("\"'").strip()
    # Common placeholders left in the field by mistake.
    if key.lower() in (
        "gemini_api_key",
        "your-api-key",
        "your_api_key",
        "api_key",
        "openai_api_key",
        "<api-key>",
        "xxx",
    ):
        return ""
    return key


def normalize_ai_base_url(url: str) -> str:
    """Normalize an OpenAI-compatible API root (…/v1 or vendor equivalent)."""
    u = (url or DEFAULT_AI_BASE_URL).strip().rstrip("/")
    if not u:
        return DEFAULT_AI_BASE_URL
    low = u.lower()
    # Allow pasting the full chat completions URL.
    for suffix in ("/chat/completions", "/completions"):
        if low.endswith(suffix):
            u = u[: -len(suffix)].rstrip("/")
            low = u.lower()
            break
    # Ollama's native root (…/api) is not the OpenAI-compatible one.
    if low.endswith("/api"):
        u = u[:-4].rstrip("/")
        low = u.lower()
    # A bare host (no path) means the vendor's /v1 root.
    host_only = low.split("://", 1)[-1]
    if "/" not in host_only:
        u = u + "/v1"
    return u


def resolve_ai_api_key(api_key: Optional[str] = None) -> str:
    """*api_key*, else ``OPENAI_API_KEY`` / ``GEMINI_API_KEY`` / ``OLLAMA_API_KEY``."""
    key = normalize_api_key(api_key)
    for env_name in ("OPENAI_API_KEY", "GEMINI_API_KEY", "OLLAMA_API_KEY"):
        if key:
            break
        key = normalize_api_key(os.environ.get(env_name, ""))
    return key


def ai_request_headers(
    api_key: Optional[str] = None,
    *,
    base_url: str = "",
) -> Dict[str, str]:
    """JSON headers plus a Bearer token when a key is configured.

    Gemini OpenAI-compat (``…/v1beta/openai``) must use **only**
    ``Authorization: Bearer`` — also sending ``x-goog-api-key`` causes HTTP 400
    ("Please pass a valid API key" / "Multiple authentication credentials").
    Local Ollama needs no key at all.
    """
    headers = {"Content-Type": "application/json"}
    key = resolve_ai_api_key(api_key)
    if key:
        headers["Authorization"] = f"Bearer {key}"
    return headers


def is_local_ai_host(url: str) -> bool:
    """True for loopback endpoints (Ollama and other local servers need no key)."""
    u = normalize_ai_base_url(url)
    if "://" not in u:
        u = f"http://{u}"
    try:
        # ``hostname`` unwraps [::1] and drops the port; splitting on ':' does not.
        host = urllib.parse.urlsplit(u).hostname or ""
    except ValueError:
        return False
    return host.lower() in LOCAL_AI_HOSTS


def default_ai_auth_mode(preset_id: str = "", base_url: str = "") -> str:
    """Auth method to offer when the user has not chosen one yet."""
    pid = normalize_ai_preset(preset_id) if preset_id else ""
    if pid == AI_PRESET_OLLAMA:
        return AI_AUTH_NONE
    if base_url and is_local_ai_host(base_url):
        return AI_AUTH_NONE
    return AI_AUTH_API_KEY


def normalize_ai_auth_mode(
    value: Any,
    *,
    preset_id: str = "",
    base_url: str = "",
) -> str:
    """Map stored / imported auth method names onto ``none`` / ``api_key`` / ``browser``."""
    want = str(value or "").strip().lower().replace("-", "_").replace(" ", "_")
    aliases = {
        "none": AI_AUTH_NONE,
        "local": AI_AUTH_NONE,
        "no": AI_AUTH_NONE,
        "off": AI_AUTH_NONE,
        "api_key": AI_AUTH_API_KEY,
        "apikey": AI_AUTH_API_KEY,
        "api": AI_AUTH_API_KEY,
        "key": AI_AUTH_API_KEY,
        "token": AI_AUTH_API_KEY,
        "browser": AI_AUTH_BROWSER,
        "sign_in": AI_AUTH_BROWSER,
        "signin": AI_AUTH_BROWSER,
        "login": AI_AUTH_BROWSER,
        "oauth": AI_AUTH_BROWSER,
    }
    if want in aliases:
        return aliases[want]
    return default_ai_auth_mode(preset_id, base_url)


def parse_ai_tls_verify(value: Any, *, default: bool = True) -> bool:
    """Whether to verify the HTTPS certificate (default on)."""
    if value is None or value == "":
        return bool(default)
    if isinstance(value, bool):
        return value
    s = str(value).strip().lower()
    if s in ("0", "false", "no", "off", "disable", "disabled", "insecure"):
        return False
    if s in ("1", "true", "yes", "on", "enable", "enabled", "secure"):
        return True
    return bool(default)


def format_ai_tls_verify(value: Any, *, default: bool = True) -> str:
    return "true" if parse_ai_tls_verify(value, default=default) else "false"


def ai_ssl_context(tls_verify: bool = True):
    """``None`` uses urllib defaults; otherwise an unverified context."""
    if parse_ai_tls_verify(tls_verify, default=True):
        return None
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    return ctx


def ai_urlopen(req, timeout_s: float, *, tls_verify: bool = True):
    """``urlopen`` with optional self-signed TLS for private AI gateways."""
    kwargs: Dict[str, Any] = {"timeout": timeout_s}
    ctx = ai_ssl_context(tls_verify)
    if ctx is not None:
        kwargs["context"] = ctx
    return urllib.request.urlopen(req, **kwargs)


def _ai_ssl_error_tip(exc: BaseException, *, tls_verify: bool = True) -> str:
    msg = str(exc).lower()
    if "certificate" not in msg and "ssl" not in msg:
        return ""
    if parse_ai_tls_verify(tls_verify, default=True):
        return (
            " The endpoint presents a self-signed or private CA certificate. "
            "In Settings → AI enable Allow self-signed TLS for this preset "
            "(desktop only — browsers cannot skip certificate checks; trust "
            "the cert in the OS/browser, use http:// on a private LAN, or "
            "use the Desktop app)."
        )
    return ""


def _ai_is_timeout_error(exc: BaseException) -> bool:
    if isinstance(exc, TimeoutError):
        return True
    reason = getattr(exc, "reason", None)
    if isinstance(reason, TimeoutError):
        return True
    blob = f"{exc} {reason or ''}".lower()
    return "timed out" in blob or "timeout" in blob


def _ai_timeout_error_tip(exc: BaseException, *, timeout_s: float) -> str:
    if not _ai_is_timeout_error(exc):
        return ""
    secs = max(1, int(round(float(timeout_s) or 0)))
    return (
        f" Waited {secs}s for a non-streaming POST /chat/completions "
        "(GET /models only lists ids and does not run the model). "
        "First load of a large model is often slower — wait until it is warm "
        "and retry, or Ask in the AI tab. Confirm with curl to the same URL "
        "and body; if curl also hangs, the gateway's chat upstream is stuck. "
        "Try curl with \"stream\": true if non-stream never returns."
    )


def ai_preset_signin_url(preset_id: str, base_url: str = "") -> str:
    """Browser page to open for Sign in / Get key (Phase 1: vendor key portal)."""
    pid = normalize_ai_preset(preset_id)
    url = AI_PRESET_KEY_URLS.get(pid, "")
    if url:
        return url
    raw = str(base_url or "").strip()
    if raw.lower().startswith(("http://", "https://")):
        try:
            parts = urllib.parse.urlsplit(raw)
            if parts.scheme and parts.netloc:
                return f"{parts.scheme}://{parts.netloc}"
        except ValueError:
            pass
    return ""


def ai_preset_signin_label(preset_id: str) -> str:
    pid = normalize_ai_preset(preset_id)
    return AI_PRESET_SIGNIN_LABELS.get(pid, "Sign in…")


def ai_auth_status(
    *,
    auth_mode: str = "",
    api_key: str = "",
    base_url: str = "",
    preset_id: str = "",
) -> Dict[str, Any]:
    """Chip / CTA state for the active preset."""
    mode = normalize_ai_auth_mode(
        auth_mode, preset_id=preset_id, base_url=base_url)
    has_key = bool(resolve_ai_api_key(api_key))
    if mode == AI_AUTH_NONE:
        return {
            "mode": mode,
            "label": "Local",
            "needs_auth": False,
            "signed_in": False,
        }
    if has_key:
        if mode == AI_AUTH_BROWSER:
            return {
                "mode": mode,
                "label": "Signed in",
                "needs_auth": False,
                "signed_in": True,
            }
        return {
            "mode": mode,
            "label": "Key saved",
            "needs_auth": False,
            "signed_in": False,
        }
    return {
        "mode": mode,
        "label": "Needs sign-in" if mode == AI_AUTH_BROWSER else "Needs API key",
        "needs_auth": True,
        "signed_in": False,
    }


def normalize_ai_context(ctx: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Accept snake_case or camelCase context keys (Desktop / Web parity)."""
    c = dict(ctx or {})
    findings = c.get("findings_text")
    if findings is None or findings == "":
        findings = c.get("findingsText", "")
    return {
        "findings_text": findings or "",
        "span": c.get("span", "") or "",
        "cores": c.get("cores", ""),
        "scope": c.get("scope", "") or "",
        "metrics": c.get("metrics"),
    }


_JUMP_RE = re.compile(r"jump:([0-9]+(?:\.[0-9]+)?)")
_MD_INLINE_CODE_RE = re.compile(r"`([^`\n]+)`")
_MD_BOLD_RE = re.compile(r"(\*\*|__)(.+?)\1")
_MD_ITALIC_RE = re.compile(r"(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)|(?<!_)_(?!_)(.+?)(?<!_)_(?!_)")
_MD_LINK_RE = re.compile(r"\[([^\]]+)\]\(([^)]+)\)")


def extract_jump_times(text: str) -> List[float]:
    """Parse ``jump:NNNN`` tokens from assistant text (parity with web)."""
    out: List[float] = []
    for m in _JUMP_RE.finditer(text or ""):
        try:
            out.append(float(m.group(1)))
        except ValueError:
            continue
    return out


def ai_jump_annotation_note(value: float) -> str:
    """Annotation label for a clicked ``jump:TIME`` link (web parity)."""
    try:
        v = float(value)
    except (TypeError, ValueError):
        return "AI jump"
    if v.is_integer():
        return f"AI jump:{int(v)}"
    return f"AI jump:{value}"


def _md_inline_to_html_escaped(text: str) -> str:
    """Escape text and apply inline markdown (code, bold, italic, links, jump:N)."""
    placeholders: List[str] = []

    def _stash(frag: str) -> str:
        placeholders.append(frag)
        return f"\x00MD{len(placeholders) - 1}\x00"

    parts: List[Tuple[str, str]] = []
    last = 0
    src = text or ""
    for m in _MD_INLINE_CODE_RE.finditer(src):
        parts.append(("t", src[last:m.start()]))
        parts.append(("c", m.group(1)))
        last = m.end()
    parts.append(("t", src[last:]))

    out_chunks: List[str] = []
    for kind, val in parts:
        if kind == "c":
            out_chunks.append(_stash(f"<code>{html.escape(val)}</code>"))
            continue
        seg = val
        seglast = 0
        buf: List[str] = []
        for lm in _MD_LINK_RE.finditer(seg):
            buf.append(html.escape(seg[seglast:lm.start()]))
            label = html.escape(lm.group(1))
            href = lm.group(2).strip()
            low = href.lower()
            if (
                low.startswith("http://")
                or low.startswith("https://")
                or                 low.startswith("btfjump:")
                or low.startswith("btfhighlight:")
                or low.startswith("mailto:")
            ):
                buf.append(
                    _stash(f'<a href="{html.escape(href, quote=True)}">{label}</a>')
                )
            else:
                buf.append(html.escape(lm.group(0)))
            seglast = lm.end()
        buf.append(html.escape(seg[seglast:]))
        chunk = "".join(buf)
        chunk = _MD_BOLD_RE.sub(lambda m: f"<strong>{m.group(2)}</strong>", chunk)

        def _ital(m: re.Match) -> str:
            body = m.group(1) if m.group(1) is not None else m.group(2)
            return f"<em>{body}</em>"

        chunk = _MD_ITALIC_RE.sub(_ital, chunk)
        chunk = _JUMP_RE.sub(
            lambda m: _stash(
                f'<a href="{btf_jump_href(m.group(1))}" class="ai-jump">'
                f"jump:{m.group(1)}</a>"
            ),
            chunk,
        )
        out_chunks.append(chunk)

    result = "".join(out_chunks)
    for i, frag in enumerate(placeholders):
        result = result.replace(f"\x00MD{i}\x00", frag)
    return result


_MD_TABLE_ALIGN_RE = re.compile(r"^:?-{1,}:?$")
_HTML_TABLE_START_RE = re.compile(r"^<table\b", re.IGNORECASE)
_HTML_TABLE_END_RE = re.compile(r"</table\s*>", re.IGNORECASE)
_AI_MD_TH_STYLE = (
    "border:1px solid #3a4658;padding:4px 8px;"
    "background:#243044;color:#e8eef6;font-weight:600;"
)
_AI_MD_TD_STYLE = (
    "border:1px solid #3a4658;padding:4px 8px;"
    "background:#1a2230;color:#dbe2ea;"
)
_AI_MD_TABLE_OPEN = (
    '<table class="ai-md-table" width="100%" cellspacing="0" cellpadding="4">'
)


def _split_md_table_row(line: str) -> List[str]:
    s = (line or "").strip()
    if s.startswith("|"):
        s = s[1:]
    if s.endswith("|") and not s.endswith("\\|"):
        s = s[:-1]
    return [p.strip().replace("\\|", "|") for p in re.split(r"(?<!\\)\|", s)]


def _is_md_table_separator(line: str) -> bool:
    if "|" not in (line or ""):
        return False
    cells = _split_md_table_row(line)
    if not cells:
        return False
    for cell in cells:
        compact = re.sub(r"\s+", "", cell)
        if not compact or not _MD_TABLE_ALIGN_RE.fullmatch(compact):
            return False
    return True


def _md_table_aligns(sep_line: str, ncols: int) -> List[str]:
    cells = _split_md_table_row(sep_line)
    out: List[str] = []
    for i in range(ncols):
        compact = re.sub(r"\s+", "", cells[i]) if i < len(cells) else ""
        left = compact.startswith(":")
        right = compact.endswith(":")
        if left and right:
            out.append("center")
        elif right:
            out.append("right")
        else:
            out.append("left")
    return out


def _md_table_cell_html(tag: str, text: str, align: str) -> str:
    style = _AI_MD_TH_STYLE if tag == "th" else _AI_MD_TD_STYLE
    al = align if align in ("left", "right", "center") else "left"
    return (
        f'<{tag} align="{al}" style="{style}">'
        f"{_md_inline_to_html_escaped(text)}</{tag}>"
    )


def _md_table_html(header: List[str], aligns: List[str],
                   rows: List[List[str]]) -> str:
    ncols = max(1, len(header))

    def _pad(cells: List[str]) -> List[str]:
        padded = list(cells[:ncols])
        while len(padded) < ncols:
            padded.append("")
        return padded

    header = _pad(header)
    thead = "<tr>" + "".join(
        _md_table_cell_html("th", header[i], aligns[i] if i < len(aligns) else "left")
        for i in range(ncols)
    ) + "</tr>"
    body: List[str] = []
    for row in rows:
        cells = _pad(row)
        body.append(
            "<tr>" + "".join(
                _md_table_cell_html(
                    "td", cells[i], aligns[i] if i < len(aligns) else "left")
                for i in range(ncols)
            ) + "</tr>"
        )
    return (
        f"{_AI_MD_TABLE_OPEN}<thead>{thead}</thead>"
        f"<tbody>{''.join(body)}</tbody></table>"
    )


class _SafeAiTableHtmlParser(HTMLParser):
    """Keep table markup only; drop scripts and event-handler attributes."""

    _KEEP = frozenset({
        "table", "thead", "tbody", "tfoot", "tr", "th", "td", "caption", "br",
    })
    _SKIP_INNER = frozenset({
        "script", "style", "iframe", "object", "embed", "link", "meta", "svg",
    })

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: List[str] = []
        self._skip = 0
        self.saw_table = False

    def handle_starttag(self, tag: str, attrs) -> None:
        tag = (tag or "").lower()
        if tag in self._SKIP_INNER:
            self._skip += 1
            return
        if self._skip or tag not in self._KEEP:
            return
        if tag == "table":
            self.saw_table = True
            self.parts.append(_AI_MD_TABLE_OPEN)
            return
        if tag == "br":
            self.parts.append("<br>")
            return
        extra: List[str] = []
        align = ""
        for key, val in attrs or ():
            key = (key or "").lower()
            val = val or ""
            if key == "align" and val.lower() in ("left", "right", "center"):
                align = val.lower()
            elif key in ("colspan", "rowspan") and str(val).isdigit():
                n = int(val)
                if 1 <= n <= 32:
                    extra.append(f'{key}="{n}"')
        if tag in ("th", "td"):
            if align:
                extra.append(f'align="{align}"')
            style = _AI_MD_TH_STYLE if tag == "th" else _AI_MD_TD_STYLE
            extra.append(f'style="{style}"')
        attr = (" " + " ".join(extra)) if extra else ""
        self.parts.append(f"<{tag}{attr}>")

    def handle_endtag(self, tag: str) -> None:
        tag = (tag or "").lower()
        if tag in self._SKIP_INNER:
            self._skip = max(0, self._skip - 1)
            return
        if self._skip or tag not in self._KEEP or tag == "br":
            return
        self.parts.append(f"</{tag}>")

    def handle_startendtag(self, tag: str, attrs) -> None:
        if (tag or "").lower() == "br" and not self._skip:
            self.parts.append("<br>")
            return
        self.handle_starttag(tag, attrs)
        self.handle_endtag(tag)

    def handle_data(self, data: str) -> None:
        if self._skip or not data:
            return
        self.parts.append(_md_inline_to_html_escaped(data))


def _sanitize_html_table_block(block: str) -> str:
    parser = _SafeAiTableHtmlParser()
    try:
        parser.feed(block or "")
        parser.close()
    except Exception:
        return ""
    html_out = "".join(parser.parts).strip()
    if not parser.saw_table or "<table" not in html_out.lower():
        return ""
    return html_out


def markdown_to_safe_html(text: str, *, as_img: bool = True) -> str:
    """Convert a subset of Markdown to safe HTML (AI reply preview).

    ``as_img=True`` (QTextBrowser chat) embeds mermaid as a PNG-compatible
    data-URI ``<img>``. ``as_img=False`` (HTML export / browser) keeps an
    inline SVG so diagram nodes stay clickable.
    """
    raw = (text or "").replace("\r\n", "\n").replace("\r", "\n").strip()
    if not raw:
        return ""
    lines = raw.split("\n")
    out: List[str] = []
    i = 0
    n = len(lines)

    def _flush_para(buf: List[str]) -> None:
        if not buf:
            return
        body = "<br>".join(_md_inline_to_html_escaped(s.strip()) for s in buf)
        out.append(f"<p>{body}</p>")
        buf.clear()

    para: List[str] = []
    while i < n:
        line = lines[i]
        stripped = line.strip()

        if stripped.startswith("```"):
            _flush_para(para)
            lang = stripped[3:].strip()
            i += 1
            code_lines: List[str] = []
            while i < n and not lines[i].strip().startswith("```"):
                code_lines.append(lines[i])
                i += 1
            if i < n:
                i += 1
            if lang.lower() == "mermaid":
                out.append(mermaid_block_html(
                    "\n".join(code_lines), as_img=as_img, zoomable=as_img))
                continue
            code_html = html.escape("\n".join(code_lines))
            cls = f' class="language-{html.escape(lang)}"' if lang else ""
            out.append(f"<pre><code{cls}>{code_html}</code></pre>")
            continue

        if not stripped:
            _flush_para(para)
            i += 1
            continue

        if re.fullmatch(r"(-{3,}|\*{3,}|_{3,})", stripped):
            _flush_para(para)
            out.append("<hr>")
            i += 1
            continue

        hm = re.match(r"^(#{1,4})\s+(.+)$", stripped)
        if hm:
            _flush_para(para)
            level = len(hm.group(1))
            out.append(
                f"<h{level}>{_md_inline_to_html_escaped(hm.group(2).strip())}</h{level}>"
            )
            i += 1
            continue

        if stripped.startswith(">"):
            _flush_para(para)
            qlines: List[str] = []
            while i < n and lines[i].strip().startswith(">"):
                qlines.append(re.sub(r"^>\s?", "", lines[i].strip()))
                i += 1
            out.append(
                f"<blockquote>{_md_inline_to_html_escaped(' '.join(qlines))}</blockquote>"
            )
            continue

        if re.match(r"^[-*+]\s+", stripped) or re.match(r"^\d+\.\s+", stripped):
            _flush_para(para)
            ordered = bool(re.match(r"^\d+\.\s+", stripped))
            tag = "ol" if ordered else "ul"
            items: List[str] = []
            start_num = 0
            while i < n:
                s = lines[i].strip()
                if ordered:
                    # Models often interrupt 1./2./3. with paragraphs and nested
                    # bullets; each run becomes its own <ol>, so honour the
                    # source number via start=/value=.
                    m = re.match(r"^(\d+)\.\s+(.*)$", s)
                    if not m:
                        break
                    num = int(m.group(1))
                    if not start_num:
                        start_num = num
                    val = (
                        ""
                        if num == start_num + len(items)
                        else f' value="{num}"'
                    )
                    items.append(
                        f"<li{val}>{_md_inline_to_html_escaped(m.group(2))}</li>"
                    )
                else:
                    m = re.match(r"^[-*+]\s+(.*)$", s)
                    if not m:
                        break
                    items.append(
                        f"<li>{_md_inline_to_html_escaped(m.group(1))}</li>"
                    )
                i += 1
            start_attr = f' start="{start_num}"' if ordered and start_num > 1 else ""
            out.append(f"<{tag}{start_attr}>{''.join(items)}</{tag}>")
            continue

        if _HTML_TABLE_START_RE.match(stripped):
            _flush_para(para)
            buf = [stripped]
            found_end = bool(_HTML_TABLE_END_RE.search(stripped))
            i += 1
            while i < n and not found_end:
                buf.append(lines[i])
                if _HTML_TABLE_END_RE.search(lines[i]):
                    found_end = True
                i += 1
            block = "\n".join(buf)
            safe = _sanitize_html_table_block(block)
            if safe:
                out.append(safe)
            else:
                out.append(f"<p>{_md_inline_to_html_escaped(block)}</p>")
            continue

        if (
            "|" in stripped
            and i + 1 < n
            and _is_md_table_separator(lines[i + 1].strip())
        ):
            _flush_para(para)
            header_cells = _split_md_table_row(stripped)
            aligns = _md_table_aligns(lines[i + 1].strip(), max(1, len(header_cells)))
            i += 2
            body_rows: List[List[str]] = []
            while i < n:
                s = lines[i].strip()
                if not s or "|" not in s or s.startswith("```"):
                    break
                if re.match(r"^#{1,4}\s+", s) or _HTML_TABLE_START_RE.match(s):
                    break
                if _is_md_table_separator(s):
                    i += 1
                    continue
                body_rows.append(_split_md_table_row(s))
                i += 1
            out.append(_md_table_html(header_cells, aligns, body_rows))
            continue

        para.append(stripped)
        i += 1

    _flush_para(para)
    return "".join(out)


def _ai_message_body_html(role: str, text: str, *, as_img: bool = True) -> str:
    """Message body without the role prefix; assistant replies render as Markdown."""
    body_text = (text or "").strip()
    if role == "assistant":
        return markdown_to_safe_html(body_text, as_img=as_img) or "<p></p>"
    esc = html.escape(body_text)
    linked = _JUMP_RE.sub(
        lambda m: (
            f'<a href="{btf_jump_href(m.group(1))}" class="ai-jump">'
            f"jump:{m.group(1)}</a>"
        ),
        esc,
    )
    return linked.replace("\n", "<br>")


# QTextBrowser CSS is limited; keep selectors simple (no descendant chains).
_AI_LOG_STYLE = (
    "h1,h2,h3,h4{margin:8px 0 4px;font-size:13px;}"
    "h1{font-size:15px;}h2{font-size:14px;}"
    "p{margin:4px 0;}"
    "ul,ol{margin:4px 0 4px 18px;padding:0;}"
    "li{margin:2px 0;}"
    "pre{background:#1a2230;border:1px solid #3a4658;border-radius:4px;"
    "padding:8px;margin:6px 0;white-space:pre-wrap;}"
    "code{font-family:Menlo,Consolas,Monaco,'Courier New',monospace;font-size:11px;}"
    "p code,li code{background:rgba(127,127,127,0.18);padding:1px 4px;border-radius:3px;}"
    "blockquote{margin:6px 0;padding:4px 10px;border-left:3px solid #5b9bd5;"
    "color:#a8b4c4;}"
    "hr{border:none;border-top:1px solid #3a4658;margin:8px 0;}"
    "a{color:#5b9bd5;}"
    "table.ai-md-table{margin:8px 0;}"
    ".ai-role{font-size:11px;font-weight:600;letter-spacing:0.06em;"
    "text-transform:uppercase;}"
    ".ai-role-user{color:#6ea8e0;}"
    ".ai-role-assistant{color:#6fbf9a;}"
    ".ai-tool-card{color:#e6d48a;}"
    "img.ai-mermaid-img{max-width:100%;height:auto;border-radius:4px;}"
    "a.ai-mermaid-zoom{cursor:zoom-in;text-decoration:none;}"
)


def ai_entry_role(entry: Any) -> str:
    if isinstance(entry, dict):
        return str(entry.get("role") or "assistant")
    return str(entry[0])


def ai_entry_text(entry: Any) -> str:
    if isinstance(entry, dict):
        return str(entry.get("text") or entry.get("content") or "")
    if isinstance(entry, (list, tuple)) and len(entry) > 1:
        return str(entry[1] or "")
    return ""


def ai_entry_tools(entry: Any) -> List[Dict[str, Any]]:
    if isinstance(entry, dict):
        tools = entry.get("tools") or []
        return list(tools) if isinstance(tools, list) else []
    return []


def _tool_cards_html(tools: Sequence[Dict[str, Any]], batch_id: str) -> str:
    if not tools:
        return ""
    rows: List[str] = []
    status = "pending"
    for t in tools:
        if isinstance(t, dict) and t.get("status"):
            status = str(t.get("status") or status)
            break
    for t in tools:
        if not isinstance(t, dict):
            continue
        name = str(t.get("name") or "")
        args = t.get("arguments") if isinstance(t.get("arguments"), dict) else {}
        label = html.escape(summarise_tool_call(name, args))
        st = html.escape(str(t.get("status") or status))
        rows.append(f"<p>⚡ {label} <span style=\"color:#8b98a8\">({st})</span></p>")
    actions = ""
    if status == "pending" and batch_id:
        actions = (
            f'<p><a href="btfaction:apply/{html.escape(batch_id)}">Apply</a>'
            f' · <a href="btfaction:skip/{html.escape(batch_id)}">Skip</a></p>'
        )
    elif status == "applied" and batch_id:
        actions = (
            f'<p><a href="btfaction:undo/{html.escape(batch_id)}">Undo</a></p>'
        )
    return (
        '<table width="100%" cellspacing="0" cellpadding="0">'
        '<tr><td bgcolor="#2a2418" class="ai-tool-card" '
        'style="border-left:3px solid #c9a227;padding:8px 10px;">'
        f"{''.join(rows)}{actions}</td></tr></table>"
    )


def _format_ai_log_html(role: str, text: str, tools: Optional[Sequence[Dict[str, Any]]] = None,
                        batch_id: str = "") -> str:
    """One conversation turn as a self-contained table (Qt will not merge these)."""
    is_user = role == "user"
    label = "You" if is_user else "Assistant"
    role_cls = "ai-role-user" if is_user else "ai-role-assistant"
    # bgcolor is more reliable in QTextBrowser than CSS background on divs.
    bg = "#1e3348" if is_user else "#1a2620"
    bar = "#5b9bd5" if is_user else "#3d9a72"
    body = _ai_message_body_html(role, text) if (text or "").strip() else ""
    cards = _tool_cards_html(tools or [], batch_id)
    if not body and not cards:
        body = "<p></p>"
    return (
        f'<table class="ai-turn" width="100%" cellspacing="0" cellpadding="0">'
        f'<tr><td class="ai-role {role_cls}" style="padding:10px 0 3px 0;">{label}</td></tr>'
        f'<tr><td class="ai-bubble" bgcolor="{bg}" '
        f'style="border-left:3px solid {bar};padding:8px 10px;">{body}{cards}</td></tr>'
        f"</table>"
    )


def _ai_log_document_html(entries: Sequence[Any]) -> str:
    """Full conversation document for QTextBrowser.setHtml (avoids append merge)."""
    if not entries:
        return ""
    parts: List[str] = []
    for i, entry in enumerate(entries):
        if i:
            parts.append('<hr class="ai-turn-sep">')
        parts.append(_format_ai_log_html(
            ai_entry_role(entry),
            ai_entry_text(entry),
            ai_entry_tools(entry),
            str((entry.get("batch_id") if isinstance(entry, dict) else "") or ""),
        ))
    return f"<html><body>{''.join(parts)}</body></html>"


def _ai_file_stamp() -> str:
    return datetime.datetime.now().strftime("%Y%m%d-%H%M%S")


def _tool_transcript_lines(entry: Any) -> List[str]:
    lines: List[str] = []
    for t in ai_entry_tools(entry):
        if not isinstance(t, dict):
            continue
        name = str(t.get("name") or "")
        args = t.get("arguments") if isinstance(t.get("arguments"), dict) else {}
        st = str(t.get("status") or "pending")
        lines.append(f"- ⚡ {summarise_tool_call(name, args)} ({st})")
    return lines


def format_ai_conversation_markdown(entries: Sequence[Any]) -> str:
    """Markdown transcript of the conversation (assistant replies kept as-is)."""
    stamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    out = ["# BTF Viewer — AI Conversation", "", f"_Saved {stamp}_", ""]
    for entry in entries:
        role = ai_entry_role(entry)
        out.append("## You" if role == "user" else "## Assistant")
        out.append("")
        text = (ai_entry_text(entry) or "").strip()
        if text:
            out.append(text)
            out.append("")
        tools = _tool_transcript_lines(entry)
        if tools:
            out.extend(tools)
            out.append("")
    return "\n".join(out).rstrip() + "\n"


def format_ai_conversation_text(entries: Sequence[Any]) -> str:
    """Plain-text transcript of the conversation."""
    stamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    out = ["BTF Viewer — AI Conversation", f"Saved {stamp}", ""]
    for entry in entries:
        role = ai_entry_role(entry)
        out.append("You:" if role == "user" else "Assistant:")
        text = (ai_entry_text(entry) or "").strip()
        if text:
            out.append(text)
        tools = _tool_transcript_lines(entry)
        if tools:
            out.extend(tools)
        out.append("")
    return "\n".join(out).rstrip() + "\n"


_AI_HTML_STYLE = """
body{background:#12161d;color:#dbe2ea;font-family:system-ui,-apple-system,'Segoe UI',sans-serif;
  font-size:13px;line-height:1.5;margin:0;padding:20px;}
h1{font-size:18px;margin:0 0 4px;}
.saved{color:#8b98a8;font-size:12px;margin:0 0 16px;}
.msg{padding:12px 0;border-top:1px solid #2b3442;}
.msg:first-of-type{border-top:none;padding-top:0;}
.msg h3{font-size:11px;text-transform:uppercase;letter-spacing:.06em;margin:0 0 6px;color:#8b98a8;}
.msg.user h3{color:#6ea8e0;}
.msg.assistant h3{color:#6fbf9a;}
.msg .body{padding:8px 10px;border-left:3px solid #5b9bd5;background:#1e3348;border-radius:0 6px 6px 0;}
.msg.assistant .body{border-left-color:#3d9a72;background:#1a2620;}
pre{background:#1a2230;border:1px solid #3a4658;border-radius:4px;padding:8px;overflow:auto;}
code{font-family:Menlo,Consolas,Monaco,'Courier New',monospace;font-size:12px;}
blockquote{margin:6px 0;padding:4px 10px;border-left:3px solid #5b9bd5;color:#a8b4c4;}
a{color:#5b9bd5;}
""".strip()


def format_ai_conversation_html(entries: Sequence[Any]) -> str:
    """Standalone HTML transcript (Markdown rendered, same styling as the panel).

    Keep in sync with aiMarkdown.js::formatAiConversationHtml; Qt's own
    ``toHtml()`` would export editor-flavoured markup instead.
    """
    stamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    parts = []
    for entry in entries:
        role = ai_entry_role(entry)
        text = ai_entry_text(entry)
        head = "You" if role == "user" else "Assistant"
        cls = "user" if role == "user" else "assistant"
        body = _ai_message_body_html(role, text, as_img=False) if (text or "").strip() else ""
        cards = _tool_cards_html(ai_entry_tools(entry), "")
        parts.append(
            f'<section class="msg {cls}"><h3>{head}</h3>'
            f'<div class="body">{body}{cards}</div>'
            "</section>"
        )
    return (
        "<!DOCTYPE html>\n<html lang=\"en\">\n<head>\n"
        "<meta charset=\"utf-8\">\n"
        "<title>BTF Viewer — AI Conversation</title>\n"
        f"<style>\n{_AI_HTML_STYLE}\n</style>\n"
        "</head>\n<body>\n"
        "<h1>BTF Viewer — AI Conversation</h1>\n"
        f'<p class="saved">Saved {stamp}</p>\n'
        + "\n".join(parts)
        + "\n</body>\n</html>\n"
    )


def build_ai_user_message(
    query: str,
    *,
    findings_text: str = "",
    metrics: Optional[Dict[str, Any]] = None,
    span: str = "",
    cores: Any = "",
    scope: str = "",
) -> str:
    """Assemble the user turn: context + question."""
    parts = ["### System Trace Context"]
    if span:
        parts.append(f"- Trace Span: {span}")
    if cores != "" and cores is not None:
        parts.append(f"- Cores: {cores}")
    if scope:
        parts.append(f"- Statistics scope: {scope}")
    parts.append("")
    parts.append("### Analysis Findings")
    parts.append((findings_text or "No findings for the current scope.").rstrip())
    parts.append("")
    if metrics:
        parts.append("### Extracted Relevant Metrics")
        parts.append(json.dumps(metrics, indent=2, default=str))
        parts.append("")
    parts.append("### User Question")
    parts.append(query.strip())
    return "\n".join(parts)


def _build_chat_messages(
    query: str,
    *,
    findings_text: str = "",
    metrics: Optional[Dict[str, Any]] = None,
    span: str = "",
    cores: Any = "",
    scope: str = "",
    response_language: str = DEFAULT_AI_RESPONSE_LANGUAGE,
    history: Optional[Sequence[Dict[str, str]]] = None,
) -> List[Dict[str, str]]:
    messages: List[Dict[str, str]] = [
        {"role": "system", "content": build_ai_system_prompt(response_language)},
    ]
    if history:
        for m in history:
            role = m.get("role")
            content = m.get("content")
            if role in ("user", "assistant") and content:
                messages.append({"role": role, "content": str(content)})
    messages.append({
        "role": "user",
        "content": build_ai_user_message(
            query,
            findings_text=findings_text,
            metrics=metrics,
            span=span,
            cores=cores,
            scope=scope,
        ),
    })
    return messages


def _read_http_body(
    resp: Any,
    *,
    cancel_event: Optional[threading.Event] = None,
) -> bytes:
    chunks: List[bytes] = []
    while True:
        if cancel_event is not None and cancel_event.is_set():
            raise OllamaCancelled("Stopped")
        try:
            chunk = resp.read(16384)
        except Exception as exc:
            if cancel_event is not None and cancel_event.is_set():
                raise OllamaCancelled("Stopped") from exc
            raise
        if not chunk:
            break
        chunks.append(chunk)
    return b"".join(chunks)


def _ai_http_error_tip(code: int, detail: str = "", *, base_url: str = "") -> str:
    """Short remediation hint for OpenAI-compatible HTTP errors."""
    low = (detail or "").lower()
    host = (base_url or "").lower()
    if code in (401, 403):
        return (
            " Check authentication (Settings → AI → Sign in or API key, "
            "or OPENAI_API_KEY / GEMINI_API_KEY)."
        )
    if code == 400 and (
        "valid api key" in low or "api key" in low and "invalid" in low
        or "multiple authentication" in low
    ):
        tip = (
            " Paste a Gemini key from https://aistudio.google.com/apikey into "
            "Settings → AI → API key (OpenAI-compatible), without a Bearer prefix. "
            "Click OK to save, then Test again."
        )
        if "generativelanguage" in host or "gemini" in host:
            tip += (
                " Use Bearer-only auth (AI Studio key). If the key starts with "
                "AQ., create a new key in AI Studio (non-AQ format) — Google's "
                "OpenAI-compat endpoint still rejects some AQ. keys. "
                "Do not use an OpenAI sk- key."
            )
        return tip
    if code == 429:
        tip = (
            " Rate/quota limit (RESOURCE_EXHAUSTED). Wait and retry, check "
            "https://aistudio.google.com/rate-limit (Gemini) or your provider dashboard."
        )
        if "gemini" in host or "generativelanguage" in host or "gemini" in low:
            tip += (
                " Try model gemini-flash-lite-latest (or gemini-flash-latest). "
                "Free quota for a pinned version is often 0 or closed to new "
                "users — enable billing or switch model/project."
            )
        return tip
    if code == 404:
        tip = " Check Base URL and model name for this provider."
        if "no longer available" in low or "not found" in low:
            tip += (
                " For Gemini, prefer the rolling aliases gemini-flash-lite-latest "
                "or gemini-flash-latest; pinned versions are retired over time."
            )
        return tip
    return ""


def ai_chat_completion(
    query: str = "",
    *,
    findings_text: str = "",
    metrics: Optional[Dict[str, Any]] = None,
    span: str = "",
    cores: Any = "",
    scope: str = "",
    base_url: str = DEFAULT_AI_BASE_URL,
    model: str = DEFAULT_AI_MODEL,
    api_key: str = "",
    response_language: str = DEFAULT_AI_RESPONSE_LANGUAGE,
    timeout_s: float = AI_CHAT_TIMEOUT_S,
    history: Optional[Sequence[Dict[str, str]]] = None,
    messages: Optional[List[Dict[str, Any]]] = None,
    tools: Optional[List[Dict[str, Any]]] = None,
    preset: str = "",
    tls_verify: bool = True,
    cancel_event: Optional[threading.Event] = None,
    on_response: Optional[Callable[[Any], None]] = None,
) -> Dict[str, Any]:
    """One OpenAI-compatible ``/chat/completions`` round (non-streaming).

    Returns ``{"content", "tool_calls", "message"}``.
    """
    url_base = normalize_ai_base_url(base_url)
    url = url_base + "/chat/completions"
    chat_model = (model or DEFAULT_AI_MODEL).strip() or DEFAULT_AI_MODEL
    if not resolve_ai_api_key(api_key) and not is_local_ai_host(url_base):
        raise RuntimeError(
            "API key required for remote endpoints "
            "(Settings → AI → API key, or OPENAI_API_KEY / GEMINI_API_KEY). "
            "Paste the raw key only — no Bearer prefix."
        )
    if cancel_event is not None and cancel_event.is_set():
        raise OllamaCancelled("Stopped")
    if messages is None:
        messages = _build_chat_messages(
            query,
            findings_text=findings_text,
            metrics=metrics,
            span=span,
            cores=cores,
            scope=scope,
            response_language=response_language,
            history=history,
        )
    messages = normalize_tool_chat_messages(messages)
    if needs_gemini_thought_signatures(
            base_url=url_base, model=chat_model, preset=preset):
        messages = ensure_gemini_thought_signatures(messages)
    payload_obj: Dict[str, Any] = {
        "model": chat_model,
        "messages": messages,
        "stream": False,
    }
    use_tools = list(tools) if tools else []
    if use_tools:
        # Do not send tool_choice: Ollama/some proxies 400 on it and our old
        # retry then dropped *all* tools ("unknown" matched the error text).
        payload_obj["tools"] = use_tools

    def _post(body_obj: Dict[str, Any]) -> Dict[str, Any]:
        payload = json.dumps(body_obj).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=payload,
            headers=ai_request_headers(api_key, base_url=url_base),
            method="POST",
        )
        try:
            resp = ai_urlopen(req, timeout_s, tls_verify=tls_verify)
        except urllib.error.HTTPError as exc:
            detail = ""
            try:
                detail = exc.read().decode("utf-8", errors="replace")[:400]
            except Exception:
                pass
            tip = _ai_http_error_tip(exc.code, detail, base_url=url_base)
            err = RuntimeError(
                f"OpenAI-compatible HTTP {exc.code} at {url}: "
                f"{detail or exc.reason}.{tip}"
            )
            err.http_code = exc.code  # type: ignore[attr-defined]
            err.http_detail = detail  # type: ignore[attr-defined]
            raise err from exc
        except urllib.error.URLError as exc:
            if cancel_event is not None and cancel_event.is_set():
                raise OllamaCancelled("Stopped") from exc
            tip = _ai_ssl_error_tip(exc, tls_verify=tls_verify)
            tip += _ai_timeout_error_tip(exc, timeout_s=timeout_s)
            raise RuntimeError(
                f"Cannot reach OpenAI-compatible API at {url}.\n{exc.reason}{tip}"
            ) from exc
        except TimeoutError as exc:
            tip = _ai_timeout_error_tip(exc, timeout_s=timeout_s)
            raise RuntimeError(
                f"OpenAI-compatible request timed out after {timeout_s:.0f}s ({url}).{tip}"
            ) from exc

        if on_response is not None:
            try:
                on_response(resp)
            except Exception:
                pass
        try:
            if cancel_event is not None and cancel_event.is_set():
                raise OllamaCancelled("Stopped")
            raw = _read_http_body(resp, cancel_event=cancel_event).decode("utf-8")
            return json.loads(raw)
        finally:
            try:
                resp.close()
            except Exception:
                pass
            if on_response is not None:
                try:
                    on_response(None)
                except Exception:
                    pass

    try:
        body = _post(payload_obj)
    except RuntimeError as exc:
        detail = str(getattr(exc, "http_detail", "") or exc).lower()
        code = int(getattr(exc, "http_code", 0) or 0)
        unsupported = any(
            s in detail for s in (
                "does not support tools",
                "does not support function",
                "tool calling is not supported",
                "unsupported tool",
                "unknown field: tools",
                'unknown field "tools"',
                "unknown field 'tools'",
            )
        )
        if use_tools and code in (400, 404, 422) and unsupported:
            payload_obj.pop("tools", None)
            payload_obj.pop("tool_choice", None)
            body = _post(payload_obj)
        else:
            raise

    choices = body.get("choices") if isinstance(body, dict) else None
    msg: Dict[str, Any] = {}
    choice0: Dict[str, Any] = {}
    if isinstance(choices, list) and choices and isinstance(choices[0], dict):
        choice0 = choices[0]
        raw_msg = choice0.get("message")
        if isinstance(raw_msg, dict):
            msg = raw_msg
        elif not msg and isinstance(body.get("message"), dict):
            msg = body["message"]
    content = message_content_text(msg.get("content"))
    calls = extract_tool_calls(msg)
    if not calls and choice0.get("tool_calls"):
        calls = extract_tool_calls({"tool_calls": choice0.get("tool_calls")})
    text_calls = parse_tool_calls_from_text(content)
    calls = merge_tool_calls(calls, text_calls)
    if text_calls:
        content = strip_parsed_tool_markup(content)
    if not content and not calls:
        raise RuntimeError(f"Unexpected OpenAI-compatible response: {body!r}"[:500])
    return {"content": content, "tool_calls": calls, "message": msg}


def ai_chat(
    query: str,
    *,
    findings_text: str = "",
    metrics: Optional[Dict[str, Any]] = None,
    span: str = "",
    cores: Any = "",
    scope: str = "",
    base_url: str = DEFAULT_AI_BASE_URL,
    model: str = DEFAULT_AI_MODEL,
    api_key: str = "",
    response_language: str = DEFAULT_AI_RESPONSE_LANGUAGE,
    timeout_s: float = AI_CHAT_TIMEOUT_S,
    history: Optional[Sequence[Dict[str, str]]] = None,
    cancel_event: Optional[threading.Event] = None,
    on_response: Optional[Callable[[Any], None]] = None,
) -> str:
    """Call OpenAI-compatible ``/chat/completions`` (non-streaming)."""
    turn = ai_chat_completion(
        query,
        findings_text=findings_text,
        metrics=metrics,
        span=span,
        cores=cores,
        scope=scope,
        base_url=base_url,
        model=model,
        api_key=api_key,
        response_language=response_language,
        timeout_s=timeout_s,
        history=history,
        cancel_event=cancel_event,
        on_response=on_response,
    )
    text = str(turn.get("content") or "").strip()
    if text:
        return text
    calls = turn.get("tool_calls") or []
    if calls:
        return "\n".join(
            summarise_tool_call(c.get("name", ""), c.get("arguments") or {})
            for c in calls if isinstance(c, dict)
        )
    raise RuntimeError("Unexpected OpenAI-compatible response: empty content")


def ai_list_models(
    base_url: str = DEFAULT_AI_BASE_URL,
    timeout_s: float = AI_LIST_MODELS_TIMEOUT_S,
    api_key: str = "",
    *,
    tls_verify: bool = True,
) -> List[str]:
    """Return model ids from ``GET /models`` on an OpenAI-compatible API."""
    url_base = normalize_ai_base_url(base_url)
    url = url_base + "/models"
    req = urllib.request.Request(
        url, method="GET", headers=ai_request_headers(api_key, base_url=url_base),
    )
    try:
        with ai_urlopen(req, timeout_s, tls_verify=tls_verify) as resp:
            body = json.loads(resp.read().decode("utf-8"))
    except Exception as exc:
        tip = _ai_ssl_error_tip(exc, tls_verify=tls_verify)
        raise RuntimeError(f"Cannot list models at {url}: {exc}{tip}") from exc
    models: List[str] = []
    rows = body.get("data") if isinstance(body, dict) else None
    for m in rows or []:
        name = m.get("id") if isinstance(m, dict) else None
        if name:
            models.append(str(name))
    return models


def _model_id(name: str) -> str:
    """Model id without Gemini's ``models/`` namespace prefix."""
    n = (name or "").strip()
    return n[7:] if n[:7].lower() == "models/" else n


def match_model_name(requested: str, available: Sequence[str]) -> Optional[str]:
    """Return the served model name matching *requested*, or None.

    Ollama reports ``name:tag`` while users often type just ``name``, and
    Gemini lists ids as ``models/<id>`` while the chat API takes either form.
    """
    want = _model_id(requested)
    if not want:
        return None
    names = [str(n) for n in available if n]
    if want in names:
        return want
    want_base = want.split(":", 1)[0]
    for n in names:
        served = _model_id(n)
        if served == want or served.startswith(want + ":"):
            return n
        served_base = served.split(":", 1)[0]
        if served_base == want or (":" not in want and served_base == want_base):
            return n
    return None


def ai_test_connection(
    base_url: str = DEFAULT_AI_BASE_URL,
    model: str = DEFAULT_AI_MODEL,
    *,
    api_key: str = "",
    tls_verify: bool = True,
    timeout_s: float = AI_TEST_TIMEOUT_S,
    on_progress: Optional[Callable[[str], None]] = None,
) -> str:
    """List models, then run a tiny chat probe against the configured endpoint."""
    def _progress(msg: str) -> None:
        if on_progress is not None:
            try:
                on_progress(msg)
            except Exception:
                pass

    url_base = normalize_ai_base_url(base_url)
    model_name = (model or DEFAULT_AI_MODEL).strip() or DEFAULT_AI_MODEL
    key = resolve_ai_api_key(api_key)
    if not key and not is_local_ai_host(url_base):
        raise RuntimeError(
            "API key required for remote endpoints "
            "(Settings → AI → API key, or OPENAI_API_KEY / GEMINI_API_KEY). "
            "Paste the raw key only — no Bearer prefix."
        )

    _progress(f"1/2 Listing models at {url_base}…")
    served: List[str] = []
    listing_note = ""
    try:
        served = ai_list_models(
            url_base, timeout_s=min(AI_LIST_MODELS_TIMEOUT_S, timeout_s),
            api_key=key, tls_verify=tls_verify)
    except RuntimeError as exc:
        if is_local_ai_host(url_base):
            # Only name the canonical root when the user pointed elsewhere.
            wrong_root = (
                f" For a default Ollama install use {DEFAULT_AI_BASE_URL} "
                "(OpenAI-compatible endpoint)."
                if url_base != DEFAULT_AI_BASE_URL else ""
            )
            raise RuntimeError(
                f"{exc} Is `ollama serve` running?{wrong_root}"
            ) from exc
        listing_note = " (model list unavailable)"
    if served and match_model_name(model_name, served) is None:
        listing = ", ".join(served[:12])
        more = f" … +{len(served) - 12} more" if len(served) > 12 else ""
        raise RuntimeError(
            f"Model {model_name!r} is not served at {url_base}. "
            f"Available: {listing}{more}."
        )

    chat_url = url_base + "/chat/completions"
    _progress(
        f"2/2 Chat probe with {model_name} (first load can take a while)…"
    )
    payload = json.dumps({
        "model": model_name,
        "stream": False,
        "messages": [{"role": "user", "content": "Reply with exactly: OK"}],
        "max_tokens": 8,
    }).encode("utf-8")
    req = urllib.request.Request(
        chat_url,
        data=payload,
        headers=ai_request_headers(key, base_url=url_base),
        method="POST",
    )
    try:
        with ai_urlopen(req, timeout_s, tls_verify=tls_verify) as resp:
            body = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = ""
        try:
            detail = exc.read().decode("utf-8", errors="replace")[:300]
        except Exception:
            pass
        tip = _ai_http_error_tip(exc.code, detail, base_url=url_base)
        raise RuntimeError(
            f"HTTP {exc.code} at {chat_url}: {detail or exc.reason}.{tip}"
        ) from exc
    except Exception as exc:
        tip = _ai_ssl_error_tip(exc, tls_verify=tls_verify)
        tip += _ai_timeout_error_tip(exc, timeout_s=timeout_s)
        raise RuntimeError(
            f"Chat probe failed at {chat_url}: {exc}{tip}"
        ) from exc

    reply = ""
    choices = body.get("choices") if isinstance(body, dict) else None
    if isinstance(choices, list) and choices:
        msg = choices[0].get("message") if isinstance(choices[0], dict) else None
        if isinstance(msg, dict):
            reply = str(msg.get("content") or "").strip()
    note = f" Probe reply: {reply[:40]!r}." if reply else ""
    return f"Connected to {url_base}. Model {model_name} ready{listing_note}.{note}"


def _qtextline_cursor_x(line, pos: int) -> float:
    """Horizontal caret x. PySide ``cursorToX`` often returns ``(x, cursorPos)``."""
    raw = line.cursorToX(int(pos))
    if isinstance(raw, (tuple, list)):
        return float(raw[0]) if raw else 0.0
    return float(raw or 0.0)


def create_ai_assistant_panel(
    parent=None,
    *,
    get_context: Optional[Callable[[], Dict[str, Any]]] = None,
    get_settings: Optional[Callable[[], Dict[str, str]]] = None,
    on_open_settings: Optional[Callable[[], None]] = None,
    on_save_settings: Optional[Callable[[Dict[str, str]], None]] = None,
    on_jump: Optional[Callable[[float], None]] = None,
    on_highlight: Optional[Callable[[str], None]] = None,
    on_execute_tools: Optional[Callable[[List[Dict[str, Any]]], List[Dict[str, Any]]]] = None,
    on_undo_tools: Optional[Callable[[], None]] = None,
    on_gui_state: Optional[Callable[[], Dict[str, Any]]] = None,
    get_loaded_tabs: Optional[Callable[[], List[Dict[str, Any]]]] = None,
    build_compare_context: Optional[
        Callable[[int, int], Dict[str, Any]]
    ] = None,
):
    """Build the right-panel AI chat widget (requires Qt bindings).

    *get_loaded_tabs*: ``[{"index": int, "name": str}, ...]`` for Trace Compare.
    *build_compare_context*: ``(idx_a, idx_b) ->`` context dict like *get_context*
    with Trace Compare CSV in ``findings_text``.
    """

    class _AiLanguageDialog(QDialog):
        def __init__(self, current: str, parent_w=None) -> None:
            super().__init__(parent_w)
            self.setWindowTitle("AI response language")
            self.setModal(True)
            self.setMinimumWidth(360)
            lay = QVBoxLayout(self)
            lay.addWidget(QLabel("Preferred language for assistant replies:"))
            self._combo = QComboBox()
            self._combo.addItems(list(AI_RESPONSE_LANGUAGES))
            cur = (current or DEFAULT_AI_RESPONSE_LANGUAGE).strip()
            idx = self._combo.findText(cur)
            if idx < 0:
                self._combo.addItem(cur)
                idx = self._combo.findText(cur)
            self._combo.setCurrentIndex(max(0, idx))
            self._combo.setSizeAdjustPolicy(
                QComboBox.SizeAdjustPolicy.AdjustToContents)
            fm = self._combo.fontMetrics()
            lang_w = max((fm.horizontalAdvance(s) for s in AI_RESPONSE_LANGUAGES), default=120) + 48
            self._combo.setMinimumWidth(max(lang_w, 280))
            lay.addWidget(self._combo)
            buttons = QDialogButtonBox(
                QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
            )
            buttons.accepted.connect(self.accept)
            buttons.rejected.connect(self.reject)
            lay.addWidget(buttons)

        def selected_language(self) -> str:
            return self._combo.currentText().strip() or DEFAULT_AI_RESPONSE_LANGUAGE

    class _AiComparePickDialog(QDialog):
        """Choose two loaded tabs for the Trace Compare AI template."""

        def __init__(self, tabs: List[Dict[str, Any]], parent_w=None) -> None:
            super().__init__(parent_w)
            self.setWindowTitle("AI Trace Compare")
            self.setModal(True)
            self.setMinimumWidth(420)
            lay = QVBoxLayout(self)
            lay.addWidget(QLabel("Choose two open traces to compare:"))
            row = QHBoxLayout()
            row.addWidget(QLabel("Trace A:"))
            self._combo_a = QComboBox()
            row.addWidget(self._combo_a, 1)
            row.addWidget(QLabel("Trace B:"))
            self._combo_b = QComboBox()
            row.addWidget(self._combo_b, 1)
            lay.addLayout(row)
            for t in tabs:
                label = str(t.get("name") or f"Tab {t.get('index', '?')}")
                idx = int(t.get("index", 0))
                self._combo_a.addItem(label, idx)
                self._combo_b.addItem(label, idx)
            if len(tabs) >= 2:
                self._combo_b.setCurrentIndex(min(1, len(tabs) - 1))
            buttons = QDialogButtonBox(
                QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
            )
            ok_btn = buttons.button(QDialogButtonBox.StandardButton.Ok)
            if ok_btn is not None:
                ok_btn.setText("Compare")
            buttons.accepted.connect(self.accept)
            buttons.rejected.connect(self.reject)
            lay.addWidget(buttons)

        def selected_indices(self) -> Tuple[int, int]:
            return (
                int(self._combo_a.currentData()),
                int(self._combo_b.currentData()),
            )

    class _OllamaWorker(QObject):
        """Runs ai_chat on a plain Python thread; emits to the GUI thread.

        Avoids QThread + moveToThread + deleteLater, which can SIGSEGV in
        PySide when DeferredDelete runs on the worker thread.
        """

        finished = Signal(str)
        failed = Signal(str)
        cancelled = Signal()

        def __init__(self, parent: QObject, kwargs: dict) -> None:
            super().__init__(parent)
            self._kwargs = kwargs
            self._cancel = threading.Event()
            self._resp = None
            self._resp_lock = threading.Lock()

        def cancel(self) -> None:
            self._cancel.set()
            with self._resp_lock:
                resp = self._resp
            if resp is not None:
                try:
                    resp.close()
                except Exception:
                    pass

        def _set_resp(self, resp: Any) -> None:
            with self._resp_lock:
                self._resp = resp

        def start(self) -> None:
            threading.Thread(target=self._run, name="ai-chat", daemon=True).start()

        def _run(self) -> None:
            try:
                turn = ai_chat_completion(
                    **self._kwargs,
                    cancel_event=self._cancel,
                    on_response=self._set_resp,
                )
                if self._cancel.is_set():
                    self.cancelled.emit()
                else:
                    self.finished.emit(json.dumps(turn, default=str))
            except OllamaCancelled:
                self.cancelled.emit()
            except Exception as exc:
                if self._cancel.is_set():
                    self.cancelled.emit()
                else:
                    self.failed.emit(str(exc))

    class AiAssistantPanel(QWidget):
        def __init__(self) -> None:
            super().__init__(parent)
            self.setMinimumWidth(0)
            self._busy = False
            self._worker: Optional[_OllamaWorker] = None
            self._entries: List[Any] = []
            self._chat_messages: List[Dict[str, Any]] = []
            self._tool_round = 0
            self._pending_batches: Dict[str, Dict[str, Any]] = {}
            self._batch_seq = 0

            root = QVBoxLayout(self)
            root.setContentsMargins(6, 6, 6, 6)
            root.setSpacing(6)

            title_row = QHBoxLayout()
            title_row.setContentsMargins(0, 0, 0, 0)
            title_row.setSpacing(8)
            title = QLabel("AI Assistant")
            title.setStyleSheet("font-weight:600;")
            title_row.addWidget(title)
            self._auth_chip = QPushButton("")
            self._auth_chip.setObjectName("ai_auth_chip")
            self._auth_chip.setCursor(Qt.CursorShape.PointingHandCursor)
            self._auth_chip.setToolTip("Open Settings → AI to sign in or change the API key")
            self._auth_chip.setStyleSheet(
                "QPushButton#ai_auth_chip {"
                "  background: transparent; color: #8b98a8;"
                "  border: 1px solid #3a4658; border-radius: 10px;"
                "  padding: 1px 8px; font-size: 11px;"
                "}"
                "QPushButton#ai_auth_chip:hover { color: #dbe2ea; border-color: #5b9bd5; }"
            )
            self._auth_chip.clicked.connect(self._on_auth_chip)
            title_row.addWidget(self._auth_chip)
            title_row.addStretch(1)
            root.addLayout(title_row)

            # Match web: title, then actions above the scroll area.
            # objectName "aiActions" is excluded from dock width-relax (Ignored
            # policy + stretch was collapsing these buttons to 0 width).
            actions_host = QWidget()
            actions_host.setObjectName("aiActions")
            actions_wrap = QVBoxLayout(actions_host)
            actions_wrap.setContentsMargins(0, 0, 0, 0)
            actions_wrap.setSpacing(4)

            def _ai_action_btn(label: str, tip: str, *, primary: bool = False) -> QPushButton:
                btn = QPushButton(label)
                btn.setObjectName("ai_action_btn")
                btn.setToolTip(tip)
                btn.setCursor(Qt.CursorShape.PointingHandCursor)
                btn.setSizePolicy(QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Fixed)
                btn.setMinimumHeight(24)
                if primary:
                    btn.setDefault(True)
                    btn.setStyleSheet(
                        "QPushButton#ai_action_btn {"
                        "  background: #2a6fb2; color: #ffffff;"
                        "  border: 1px solid #1a5a9a; border-radius: 3px;"
                        "  padding: 3px 10px; font-weight: 600;"
                        "}"
                        "QPushButton#ai_action_btn:hover { background: #1a5a9a; }"
                        "QPushButton#ai_action_btn:disabled {"
                        "  background: #555555; color: #bbbbbb; border-color: #555555;"
                        "}"
                    )
                return btn

            row1 = QHBoxLayout()
            row1.setContentsMargins(0, 0, 0, 0)
            row1.setSpacing(4)
            self._clear_btn = _ai_action_btn("Clear", "Clear the conversation log")
            self._clear_btn.clicked.connect(self.clear_conversation)
            row1.addWidget(self._clear_btn)
            self._stop_btn = _ai_action_btn("Stop", "Stop the current Ollama query")
            self._stop_btn.setEnabled(False)
            self._stop_btn.clicked.connect(self.stop_query)
            row1.addWidget(self._stop_btn)
            self._send_btn = _ai_action_btn(
                "Ask", "Send the question below (Ctrl/Cmd+Enter)", primary=True)
            self._send_btn.clicked.connect(self.send_current)
            row1.addWidget(self._send_btn)
            self._lang_btn = _ai_action_btn(
                "Language…", "Preferred language for assistant replies")
            self._lang_btn.clicked.connect(self._choose_language)
            row1.addWidget(self._lang_btn)
            self._settings_btn = _ai_action_btn(
                "Settings…", "Configure the AI preset, endpoint, and model")
            self._settings_btn.clicked.connect(self._open_settings)
            row1.addWidget(self._settings_btn)
            row1.addStretch(1)
            actions_wrap.addLayout(row1)

            root.addWidget(actions_host)

            # Middle content scrolls so header actions (Clear / Stop / Ask) stay visible.
            mid_scroll = QScrollArea()
            mid_scroll.setWidgetResizable(True)
            mid_scroll.setFrameShape(QFrame.Shape.NoFrame)
            mid_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
            mid = QWidget()
            mid_lay = QVBoxLayout(mid)
            mid_lay.setContentsMargins(0, 0, 0, 0)
            mid_lay.setSpacing(6)

            hint = QLabel(
                "Uses Analysis Findings for the current Statistics scope "
                "(Trace Compare template uses compare CSV). "
                "Configure the endpoint in Settings → AI."
            )
            hint.setWordWrap(True)
            hint.setStyleSheet("color:#999;font-size:11px;")
            mid_lay.addWidget(hint)

            tpl_label = QLabel("Templates")
            tpl_label.setStyleSheet("font-weight:600;margin-top:2px;")
            mid_lay.addWidget(tpl_label)

            # Two columns: the labels are short, and a single column pushed the
            # conversation log off the bottom of a narrow dock.
            tpl_grid = QGridLayout()
            tpl_grid.setContentsMargins(0, 0, 0, 0)
            tpl_grid.setHorizontalSpacing(4)
            tpl_grid.setVerticalSpacing(4)
            tpl_grid.setColumnStretch(0, 1)
            tpl_grid.setColumnStretch(1, 1)

            self._template_btns: List[QPushButton] = []
            self._compare_btn: Optional[QPushButton] = None
            for _pos, (_tid, label, prompt) in enumerate(AI_TEMPLATE_QUESTIONS):
                btn = QPushButton(label)
                btn.setToolTip(prompt)
                btn.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
                btn.clicked.connect(
                    lambda _=False, t=_tid, p=prompt: self._use_template(t, p)
                )
                tpl_grid.addWidget(btn, _pos // 2, _pos % 2)
                self._template_btns.append(btn)
                if _tid == AI_COMPARE_TEMPLATE_ID:
                    self._compare_btn = btn
            mid_lay.addLayout(tpl_grid)

            self.refresh_template_availability()

            self._log = QTextBrowser()
            self._log.setReadOnly(True)
            self._log.setOpenExternalLinks(False)
            self._log.setOpenLinks(False)
            self._log.setPlaceholderText("Conversation appears here…")
            self._log.setMinimumHeight(100)
            self._log.document().setDefaultStyleSheet(_AI_LOG_STYLE)
            self._log.anchorClicked.connect(self._on_jump_link)
            self._log.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
            self._log.customContextMenuRequested.connect(self._show_log_menu)
            self._log.viewport().installEventFilter(self)
            mid_lay.addWidget(self._log, 1)

            self._tool_bar = QWidget()
            tool_row = QHBoxLayout(self._tool_bar)
            tool_row.setContentsMargins(0, 0, 0, 0)
            tool_row.setSpacing(6)
            self._apply_tools_btn = QPushButton("Apply GUI actions")
            self._apply_tools_btn.setToolTip("Run the pending viewer tools from the last reply")
            self._apply_tools_btn.clicked.connect(self._apply_pending_tools)
            self._skip_tools_btn = QPushButton("Skip")
            self._skip_tools_btn.clicked.connect(self._skip_pending_tools)
            self._undo_tools_btn = QPushButton("Undo last actions")
            self._undo_tools_btn.clicked.connect(self._undo_last_tools)
            tool_row.addWidget(self._apply_tools_btn)
            tool_row.addWidget(self._skip_tools_btn)
            tool_row.addWidget(self._undo_tools_btn)
            tool_row.addStretch(1)
            self._tool_bar.hide()
            mid_lay.addWidget(self._tool_bar)

            mid_scroll.setWidget(mid)
            root.addWidget(mid_scroll, 1)

            self._input = QPlainTextEdit()
            self._input.setPlaceholderText("Ask about this trace… (Ctrl/Cmd+Enter to send)")
            self._input.setFixedHeight(64)
            self._input.installEventFilter(self)
            self._input.textChanged.connect(self._refresh_send_btn)
            root.addWidget(self._input)

            self._status = QLabel("")
            self._status.setStyleSheet("color:#999;font-size:11px;")
            self._status.setWordWrap(True)
            root.addWidget(self._status)

            self._auth_cta = QWidget()
            cta_row = QHBoxLayout(self._auth_cta)
            cta_row.setContentsMargins(0, 0, 0, 0)
            cta_row.setSpacing(6)
            self._auth_cta_signin = QPushButton("Sign in…")
            self._auth_cta_signin.setToolTip("Open the provider sign-in page")
            self._auth_cta_signin.clicked.connect(self._open_signin_page)
            self._auth_cta_settings = QPushButton("Settings…")
            self._auth_cta_settings.clicked.connect(self._open_settings)
            cta_row.addWidget(self._auth_cta_signin)
            cta_row.addWidget(self._auth_cta_settings)
            cta_row.addStretch(1)
            self._auth_cta.hide()
            self._auth_forced = False
            root.addWidget(self._auth_cta)
            self._refresh_auth_chip()

            self._refresh_send_btn()

        def eventFilter(self, obj, event):  # noqa: N802
            inp = getattr(self, "_input", None)
            if inp is not None and obj is inp and event.type() == QEvent.Type.KeyPress:
                key = event.key()
                mods = event.modifiers()
                if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter) and (
                    mods & (Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.MetaModifier)
                ):
                    self.send_current()
                    return True
            log = getattr(self, "_log", None)
            if (
                log is not None
                and obj is log.viewport()
                and event.type() == QEvent.Type.MouseButtonPress
                and event.button() == Qt.MouseButton.LeftButton
            ):
                pos = event.position().toPoint() if hasattr(event, "position") else event.pos()
                if self._try_mermaid_node_click(pos):
                    return True
            return QWidget.eventFilter(self, obj, event)

        def _try_mermaid_node_click(self, view_pos) -> bool:
            href = self._log.anchorAt(view_pos) or ""
            m = re.search(
                r"btfmermaid:(?://)?zoom[/:]([^?\s#]+)",
                href,
                re.IGNORECASE,
            )
            if not m:
                return False
            src = decode_mermaid_zoom_token(urllib.parse.unquote(m.group(1)))
            if not src:
                return False
            local = self._mermaid_img_local_pos(view_pos)
            if local is None:
                return False
            hit = hit_test_mermaid(src, local[0], local[1])
            if not hit:
                return False
            _kind, value = hit
            self._on_jump_link(QUrl(f"btfhighlight:{urllib.parse.quote(value, safe='')}"))
            return True

        def _mermaid_img_local_pos(self, view_pos) -> Optional[Tuple[float, float]]:
            log = self._log
            cur = log.cursorForPosition(view_pos)
            block = cur.block()
            br = log.document().documentLayout().blockBoundingRect(block)
            it = block.begin()
            img_rect = None
            while not it.atEnd():
                frag = it.fragment()
                fmt = frag.charFormat()
                if fmt.isImageFormat():
                    rel = frag.position() - block.position()
                    tl = block.layout()
                    imgf = fmt.toImageFormat()
                    w = float(imgf.width() or 0)
                    h = float(imgf.height() or 0)
                    if w > 0 and h > 0 and tl is not None:
                        for li in range(tl.lineCount()):
                            line = tl.lineAt(li)
                            if line.textStart() <= rel < line.textStart() + max(line.textLength(), 1):
                                x1 = _qtextline_cursor_x(line, rel)
                                img_rect = QRectF(
                                    br.x() + line.x() + x1,
                                    br.y() + line.y(),
                                    w,
                                    h,
                                )
                                break
                    if img_rect is not None:
                        break
                it += 1
            if img_rect is None:
                return None
            doc_x = view_pos.x() + log.horizontalScrollBar().value()
            doc_y = view_pos.y() + log.verticalScrollBar().value()
            if not img_rect.contains(doc_x, doc_y):
                if img_rect.contains(float(view_pos.x()), float(view_pos.y())):
                    return (
                        float(view_pos.x()) - img_rect.x(),
                        float(view_pos.y()) - img_rect.y(),
                    )
                return None
            return doc_x - img_rect.x(), doc_y - img_rect.y()

        def _active_ai_settings(self) -> Dict[str, str]:
            return resolve_ai_settings(self._settings_dict())

        def _refresh_auth_chip(self) -> None:
            active = self._active_ai_settings()
            _id, label, _b, _m = ai_preset_info(active["preset"])
            st = ai_auth_status(
                auth_mode=active.get("auth_mode", ""),
                api_key=active.get("api_key", ""),
                base_url=active.get("base_url", ""),
                preset_id=active["preset"],
            )
            self._auth_chip.setText(f"{label} · {st['label']}")
            needs = bool(st["needs_auth"]) or bool(getattr(self, "_auth_forced", False))
            self._auth_cta.setVisible(needs)
            url = ai_preset_signin_url(active["preset"], active.get("base_url", ""))
            self._auth_cta_signin.setVisible(
                st["mode"] == AI_AUTH_BROWSER or bool(url)
            )
            self._auth_cta_signin.setText(ai_preset_signin_label(active["preset"]))

        def _on_auth_chip(self) -> None:
            self._open_settings()

        def _open_signin_page(self) -> None:
            active = self._active_ai_settings()
            url = ai_preset_signin_url(active["preset"], active.get("base_url", ""))
            if url:
                QDesktopServices.openUrl(QUrl(url))
                self._status.setText(
                    f"Opened {url}. Paste the key or token in Settings → AI.")
            else:
                self._status.setText(
                    "This preset has no sign-in page. Paste a token in Settings → AI.")
            self._open_settings()

        def _open_settings(self) -> None:
            if on_open_settings:
                on_open_settings()

        def _choose_language(self) -> None:
            cfg = self._settings_dict()
            current = cfg.get("response_language", DEFAULT_AI_RESPONSE_LANGUAGE)
            dlg = _AiLanguageDialog(current, self)
            if dlg.exec() != QDialog.DialogCode.Accepted:
                return
            lang = dlg.selected_language()
            if on_save_settings:
                on_save_settings({"response_language": lang})
            self._status.setText(f"Reply language: {lang}")

        def _on_jump_link(self, url: QUrl) -> None:
            scheme = (url.scheme() or "").lower()
            if scheme in ("http", "https", "mailto"):
                QDesktopServices.openUrl(url)
                return
            if scheme == "btfmermaid":
                raw = url.toString()
                m = re.search(
                    r"btfmermaid:(?://)?zoom[/:]([^?\s#]+)",
                    raw,
                    re.IGNORECASE,
                )
                token = urllib.parse.unquote(m.group(1)) if m else ""
                src = decode_mermaid_zoom_token(token)
                if src:
                    self._open_mermaid_zoom(src)
                return
            if scheme == "btfaction":
                raw = url.toString()
                m = re.search(
                    r"btfaction:(?://)?(apply|skip|undo)[/:]([^?\s#]+)",
                    raw,
                    re.IGNORECASE,
                )
                if m:
                    self._on_tool_action(m.group(1).lower(), urllib.parse.unquote(m.group(2)))
                return
            if scheme == "btfhighlight":
                name = parse_btf_highlight_href(url.toString())
                if on_highlight and name:
                    on_highlight(name)
                return
            if not on_jump or scheme != "btfjump":
                return
            value = parse_btf_jump_href(url.toString())
            if value is None:
                return
            on_jump(value)

        def _open_mermaid_zoom(self, source: str) -> None:
            dlg = _MermaidZoomDialog(source, self, on_link=self._on_jump_link)
            dlg.exec()

        def _pending_batch_id(self) -> str:
            for bid, batch in reversed(list(self._pending_batches.items())):
                tools = batch.get("tools") or []
                if any(str(t.get("status") or "pending") == "pending" for t in tools if isinstance(t, dict)):
                    return str(bid)
            return ""

        def _applied_batch_id(self) -> str:
            for bid, batch in reversed(list(self._pending_batches.items())):
                tools = batch.get("tools") or []
                if any(str(t.get("status") or "") == "applied" for t in tools if isinstance(t, dict)):
                    return str(bid)
            return ""

        def _refresh_tool_bar(self) -> None:
            bar = getattr(self, "_tool_bar", None)
            if bar is None:
                return
            pending = self._pending_batch_id()
            applied = self._applied_batch_id()
            self._apply_tools_btn.setVisible(bool(pending))
            self._skip_tools_btn.setVisible(bool(pending))
            self._undo_tools_btn.setVisible(bool(applied) and not pending)
            bar.setVisible(bool(pending or applied))

        def _apply_pending_tools(self) -> None:
            bid = self._pending_batch_id()
            if bid:
                self._on_tool_action("apply", bid)

        def _skip_pending_tools(self) -> None:
            bid = self._pending_batch_id()
            if bid:
                self._on_tool_action("skip", bid)

        def _undo_last_tools(self) -> None:
            bid = self._applied_batch_id()
            if bid:
                self._on_tool_action("undo", bid)

        def _refresh_log(self) -> None:
            """Rebuild the log from entries. QTextBrowser.append() merges HTML blocks."""
            if not self._entries:
                self._log.clear()
                self._refresh_tool_bar()
                return
            self._log.document().setDefaultStyleSheet(_AI_LOG_STYLE)
            self._log.setHtml(_ai_log_document_html(self._entries))
            bar = self._log.verticalScrollBar()
            bar.setValue(bar.maximum())
            self._refresh_tool_bar()

        def _append(self, role: str, text: str, **extra: Any) -> None:
            if extra:
                entry: Any = {"role": role, "text": text}
                entry.update(extra)
                self._entries.append(entry)
            else:
                self._entries.append((role, text))
            self._refresh_log()

        def clear_conversation(self) -> None:
            """Clear the conversation log (also stops an in-flight query)."""
            if self._busy:
                self.stop_query()
            self._entries.clear()
            self._chat_messages = []
            self._pending_batches.clear()
            self._tool_round = 0
            self._log.clear()
            self._status.setText("")
            self._refresh_tool_bar()

        def _show_log_menu(self, pos) -> None:
            menu = self._log.createStandardContextMenu(pos)
            menu.addSeparator()
            copy_all = menu.addAction("Copy conversation")
            copy_all.setEnabled(bool(self._entries))
            copy_all.triggered.connect(self.copy_conversation)
            menu.addSeparator()
            has_log = bool(self._entries)
            save_md = menu.addAction("Save As Markdown…")
            save_md.setEnabled(has_log)
            save_md.triggered.connect(lambda: self.save_conversation_as("md"))
            save_txt = menu.addAction("Save As Text…")
            save_txt.setEnabled(has_log)
            save_txt.triggered.connect(lambda: self.save_conversation_as("txt"))
            save_html = menu.addAction("Save As HTML…")
            save_html.setEnabled(has_log)
            save_html.triggered.connect(lambda: self.save_conversation_as("html"))
            menu.exec(self._log.mapToGlobal(pos))

        def copy_conversation(self) -> None:
            """Copy the whole conversation to the clipboard as Markdown."""
            if not self._entries:
                return
            clip = QApplication.clipboard()
            if clip is None:
                self._status.setText("Clipboard is not available.")
                return
            clip.setText(format_ai_conversation_markdown(self._entries))
            self._status.setText("Copied to clipboard.")

        def save_conversation_as(self, preferred: str = "") -> None:
            """Write the conversation to Markdown, plain text or HTML."""
            if not self._entries:
                return
            kind = (preferred or "").lower()
            stamp = _ai_file_stamp()
            if kind == "txt":
                start = f"ai-conversation-{stamp}.txt"
                filters = "Text files (*.txt);;Markdown (*.md);;HTML (*.html);;All files (*)"
            elif kind in ("html", "htm"):
                start = f"ai-conversation-{stamp}.html"
                filters = "HTML (*.html);;Markdown (*.md);;Text files (*.txt);;All files (*)"
            else:
                start = f"ai-conversation-{stamp}.md"
                filters = "Markdown (*.md);;Text files (*.txt);;HTML (*.html);;All files (*)"
            path, selected = QFileDialog.getSaveFileName(
                self,
                "Save AI Conversation",
                start,
                filters,
            )
            if not path:
                return
            lower = path.lower()
            if not lower.endswith((".md", ".txt", ".html", ".htm")):
                ext = ".txt" if "Text" in selected else (
                    ".html" if "HTML" in selected else ".md")
                path += ext
                lower = path.lower()
            if lower.endswith((".html", ".htm")):
                data = format_ai_conversation_html(self._entries)
            elif lower.endswith(".txt"):
                data = format_ai_conversation_text(self._entries)
            else:
                data = format_ai_conversation_markdown(self._entries)
            try:
                with open(path, "w", encoding="utf-8") as fh:
                    fh.write(data)
            except OSError as exc:
                QMessageBox.warning(
                    self, "Save failed", f"Could not write file:\n{exc}")
                return
            self._status.setText(f"Saved conversation to {os.path.basename(path)}")

        def _export_ai_report(self, args: Dict[str, Any]) -> Dict[str, Any]:
            """Write findings + GUI state + conversation (export_report tool)."""
            fmt = str((args or {}).get("format") or "html").strip().lower()
            if fmt not in ("html", "csv"):
                fmt = "html"
            gui: Dict[str, Any] = {}
            if on_gui_state:
                try:
                    gui = dict(on_gui_state() or {})
                except Exception as exc:
                    return tool_result_payload(False, f"GUI state error: {exc}")
            findings = str(gui.pop("findings", "") or "")
            if not findings and get_context:
                try:
                    findings = str((get_context() or {}).get("findings_text") or "")
                except Exception:
                    findings = ""
            meta = {
                "file": gui.pop("file", "") or "",
                "span": gui.pop("span", "") or "",
                "cores": gui.pop("cores", "") or "",
                "scope": gui.pop("scope", "") or "",
            }
            annotations = (
                gui.get("annotations") if isinstance(gui.get("annotations"), list) else []
            )
            stamp = _ai_file_stamp()
            if fmt == "csv":
                start = f"ai-report-{stamp}.csv"
                filters = "CSV (*.csv);;All files (*)"
                data = build_ai_report_csv(
                    meta=meta,
                    gui=gui,
                    findings=findings,
                    annotations=annotations,
                    conversation=format_ai_conversation_text(self._entries),
                )
            else:
                start = f"ai-report-{stamp}.html"
                filters = "HTML (*.html);;All files (*)"
                conv_html = format_ai_conversation_html(self._entries)
                inner = conv_html
                if "<body>" in inner.lower():
                    low = inner.lower()
                    a = low.find("<body>")
                    b = low.rfind("</body>")
                    if a >= 0 and b > a:
                        inner = inner[a + 6:b]
                data = build_ai_report_html(
                    meta=meta,
                    gui=gui,
                    findings=findings,
                    annotations=annotations,
                    conversation_html=inner,
                )
            path, _selected = QFileDialog.getSaveFileName(
                self, "Export AI Report", start, filters)
            if not path:
                return tool_result_payload(False, "Export cancelled")
            lower = path.lower()
            if fmt == "csv" and not lower.endswith(".csv"):
                path += ".csv"
            elif fmt == "html" and not lower.endswith((".html", ".htm")):
                path += ".html"
            try:
                with open(path, "w", encoding="utf-8") as fh:
                    fh.write(data)
            except OSError as exc:
                return tool_result_payload(False, f"Could not write file: {exc}")
            base = os.path.basename(path)
            self._status.setText(f"Saved report to {base}")
            return tool_result_payload(True, f"Saved {fmt} report to {base}", path=path)

        def stop_query(self) -> None:
            """Abort the current AI request if one is running."""
            if not self._busy:
                return
            self._status.setText("Stopping…")
            worker = self._worker
            if worker is not None:
                worker.cancel()

        def _ai_is_enabled(self) -> bool:
            cfg = self._settings_dict()
            return str(cfg.get("enabled", "true")).lower() not in (
                "0", "false", "no", "off",
            )

        def _refresh_send_btn(self) -> None:
            self._send_btn.setEnabled(
                (not self._busy)
                and self._ai_is_enabled()
                and bool(self._input.toPlainText().strip())
            )

        def _set_busy(self, busy: bool) -> None:
            self._busy = busy
            enabled = self._ai_is_enabled()
            self._send_btn.setText("Waiting…" if busy else "Ask")
            self._refresh_send_btn()
            self._stop_btn.setEnabled(busy)
            self._input.setReadOnly(busy or (not enabled))
            for btn in self._template_btns:
                btn.setEnabled((not busy) and enabled)
            self.refresh_template_availability()
            if (not enabled) and (not busy):
                self._status.setText("AI is disabled in Settings → AI.")

        def refresh_enabled_state(self) -> None:
            """Re-apply enable/disable after Settings → AI changes."""
            self._set_busy(self._busy)
            self._refresh_auth_chip()

        def _loaded_tabs(self) -> List[Dict[str, Any]]:
            if not get_loaded_tabs:
                return []
            try:
                tabs = list(get_loaded_tabs() or [])
            except Exception:
                return []
            out: List[Dict[str, Any]] = []
            for t in tabs:
                if not isinstance(t, dict):
                    continue
                if t.get("index") is None:
                    continue
                out.append(t)
            return out

        def refresh_template_availability(self) -> None:
            """Enable Trace Compare only when 2+ loaded tabs exist."""
            if self._compare_btn is None:
                return
            n = len(self._loaded_tabs())
            prompt = next(
                (p for tid, _lab, p in AI_TEMPLATE_QUESTIONS if tid == AI_COMPARE_TEMPLATE_ID),
                "Trace Compare",
            )
            if self._busy or not self._ai_is_enabled():
                self._compare_btn.setEnabled(False)
                return
            if n < 2:
                self._compare_btn.setEnabled(False)
                self._compare_btn.setToolTip(
                    "Open at least two BTF tabs to use Trace Compare."
                )
            else:
                self._compare_btn.setEnabled(True)
                self._compare_btn.setToolTip(prompt)

        def showEvent(self, event) -> None:  # noqa: N802
            super().showEvent(event)
            self.refresh_enabled_state()

        def query_template(self, template_id: str) -> None:
            """Run a built-in AI template by id (toolbar Analysis / inspector)."""
            prompt = next(
                (p for tid, _lab, p in AI_TEMPLATE_QUESTIONS if tid == template_id),
                "",
            )
            if prompt:
                self._use_template(template_id, prompt)

        def query_analysis_findings(self) -> None:
            """Run the Analysis Findings template (toolbar Analysis → Query with AI)."""
            self.query_template("findings")

        def query_migration_thrash(self) -> None:
            """Run the Migration thrash template (inspector → Query with AI)."""
            self.query_template("migrations")

        def query_trace_compare(self, idx_a: int, idx_b: int) -> None:
            """Run the Trace Compare template for two already-chosen tabs."""
            prompt = next(
                (p for tid, _lab, p in AI_TEMPLATE_QUESTIONS
                 if tid == AI_COMPARE_TEMPLATE_ID),
                "",
            )
            if prompt:
                self._run_compare_template(prompt, idx_a=idx_a, idx_b=idx_b)

        def _use_template(self, template_id: str, prompt: str) -> None:
            if self._busy:
                return
            if template_id == AI_COMPARE_TEMPLATE_ID:
                self._run_compare_template(prompt)
                return
            self._input.setPlainText(prompt)
            self.send_current()

        def _run_compare_template(
            self,
            prompt: str,
            idx_a: Optional[int] = None,
            idx_b: Optional[int] = None,
        ) -> None:
            tabs = self._loaded_tabs()
            if len(tabs) < 2:
                self._status.setText("Open at least two BTF tabs to compare.")
                self.refresh_template_availability()
                return
            if idx_a is not None and idx_b is not None:
                idx_a, idx_b = int(idx_a), int(idx_b)
                if idx_a == idx_b:
                    self._status.setText("Choose two different traces.")
                    return
            elif len(tabs) == 2:
                idx_a = int(tabs[0]["index"])
                idx_b = int(tabs[1]["index"])
            else:
                dlg = _AiComparePickDialog(tabs, self)
                if dlg.exec() != QDialog.DialogCode.Accepted:
                    return
                idx_a, idx_b = dlg.selected_indices()
                if idx_a == idx_b:
                    self._status.setText("Choose two different traces.")
                    return
            if not build_compare_context:
                self._status.setText("Trace Compare is not available.")
                return
            try:
                ctx = dict(build_compare_context(idx_a, idx_b) or {})
            except Exception as exc:
                self._status.setText(f"Compare context error: {exc}")
                return
            ctx = normalize_ai_context(ctx)
            if not (ctx.get("findings_text") or "").strip():
                self._status.setText("Could not build Trace Compare tables.")
                return
            self._input.clear()
            self._send_query(prompt, ctx)

        def _settings_dict(self) -> Dict[str, str]:
            if get_settings:
                return dict(get_settings() or {})
            return {
                "enabled": "true",
                "preset": DEFAULT_AI_PRESET,
                "response_language": DEFAULT_AI_RESPONSE_LANGUAGE,
            }

        def _on_ok(self, payload: str) -> None:
            self._auth_forced = False
            self._refresh_auth_chip()
            try:
                turn = json.loads(payload) if isinstance(payload, str) else {}
            except (TypeError, ValueError):
                turn = {"content": str(payload or ""), "tool_calls": []}
            if not isinstance(turn, dict):
                turn = {"content": str(payload or ""), "tool_calls": []}
            text = str(turn.get("content") or "").strip()
            calls = turn.get("tool_calls") if isinstance(turn.get("tool_calls"), list) else []
            if calls:
                self._chat_messages.append(
                    canonical_assistant_tool_message(text, calls)
                )
            elif text:
                self._chat_messages.append({"role": "assistant", "content": text})

            tools_norm: List[Dict[str, Any]] = []
            for c in calls:
                if not isinstance(c, dict):
                    continue
                name = str(c.get("name") or "")
                args = c.get("arguments") if isinstance(c.get("arguments"), dict) else {}
                ok_args, err = validate_tool_call(name, args)
                tools_norm.append({
                    "id": str(c.get("id") or f"call_{len(tools_norm)}"),
                    "name": name,
                    "arguments": ok_args or args,
                    "error": err,
                    "status": "pending",
                })

            auto = (
                parse_ai_auto_apply(self._settings_dict().get("auto_apply"))
                or tool_batch_auto_runs(tools_norm)
            )
            if tools_norm:
                self._batch_seq += 1
                batch_id = f"b{self._batch_seq}"
                self._pending_batches[batch_id] = {
                    "tools": tools_norm,
                    "entry_index": len(self._entries),
                }
                self._append("assistant", text, tools=tools_norm, batch_id=batch_id)
                if auto:
                    self._cleanup_worker()
                    self._apply_tool_batch(batch_id, skipped=False)
                    return
                self._status.setText("Review GUI actions, then Apply or Skip.")
                self._cleanup_worker()
                return

            if text:
                self._append("assistant", text)
            jumps = extract_jump_times(text)
            if jumps:
                token = _JUMP_RE.search(text or "")
                label = token.group(1) if token else f"{jumps[0]:g}"
                self._status.setText(
                    f"Done. Click jump:{label} to annotate the timeline and jump there."
                )
            else:
                self._status.setText("Done.")
            self._cleanup_worker()

        def _on_tool_action(self, action: str, batch_id: str) -> None:
            action = (action or "").lower()
            if action == "apply":
                self._apply_tool_batch(batch_id, skipped=False)
            elif action == "skip":
                self._apply_tool_batch(batch_id, skipped=True)
            elif action == "undo":
                if on_undo_tools:
                    on_undo_tools()
                batch = self._pending_batches.get(batch_id)
                if batch:
                    for t in batch.get("tools") or []:
                        t["status"] = "undone"
                    idx = int(batch.get("entry_index", -1))
                    if 0 <= idx < len(self._entries) and isinstance(self._entries[idx], dict):
                        self._entries[idx]["tools"] = batch["tools"]
                    self._refresh_log()
                self._status.setText("Reverted last AI GUI actions.")

        def _apply_tool_batch(self, batch_id: str, *, skipped: bool) -> None:
            batch = self._pending_batches.get(batch_id)
            if not batch:
                return
            tools = list(batch.get("tools") or [])
            results: List[Dict[str, Any]] = []
            if skipped:
                for t in tools:
                    t["status"] = "skipped"
                    results.append(tool_result_payload(False, "User declined to apply this GUI action."))
            elif on_execute_tools or any(is_export_tool(str(t.get("name") or "")) for t in tools):
                host_tools = [t for t in tools if not is_export_tool(str(t.get("name") or ""))]
                host_results: List[Dict[str, Any]] = []
                if host_tools and on_execute_tools:
                    try:
                        host_results = list(on_execute_tools(host_tools) or [])
                    except Exception as exc:
                        host_results = [tool_result_payload(False, str(exc)) for _ in host_tools]
                hi = 0
                for t in tools:
                    if is_export_tool(str(t.get("name") or "")):
                        results.append(self._export_ai_report(
                            t.get("arguments") if isinstance(t.get("arguments"), dict) else {}))
                    else:
                        res = (
                            host_results[hi]
                            if hi < len(host_results) and isinstance(host_results[hi], dict)
                            else tool_result_payload(False, "missing tool result")
                        )
                        hi += 1
                        results.append(res)
                for i, t in enumerate(tools):
                    res = results[i] if i < len(results) and isinstance(results[i], dict) else {}
                    t["status"] = "applied" if res.get("ok", True) else "failed"
                    t["result"] = res.get("message", "")
            else:
                for t in tools:
                    t["status"] = "skipped"
                    results.append(tool_result_payload(False, "No GUI dispatcher."))
            idx = int(batch.get("entry_index", -1))
            if 0 <= idx < len(self._entries) and isinstance(self._entries[idx], dict):
                self._entries[idx]["tools"] = tools
            self._refresh_log()

            for t, res in zip(tools, results or [tool_result_payload(False, "")] * len(tools)):
                self._chat_messages.append(tool_result_message(
                    tool_call_id=str(t.get("id") or ""),
                    name=str(t.get("name") or ""),
                    content=format_tool_result_content(
                        res if isinstance(res, dict) else tool_result_payload(False, str(res))
                    ),
                ))
            if skipped:
                self._status.setText("Skipped GUI actions.")
                self._cleanup_worker()
                return
            if self._tool_round >= max_tool_rounds():
                self._status.setText("Done (tool round limit).")
                self._cleanup_worker()
                return
            self._tool_round += 1
            self._continue_with_messages()

        def _continue_with_messages(self) -> None:
            cfg = self._settings_dict()
            active = resolve_ai_settings(cfg)
            kwargs = {
                "query": "",
                "messages": list(self._chat_messages),
                "tools": ai_viewer_tools(),
                "base_url": active["base_url"],
                "model": active["model"],
                "api_key": active["api_key"],
                "preset": active["preset"],
                "tls_verify": parse_ai_tls_verify(active.get("tls_verify")),
                "response_language": cfg.get(
                    "response_language", DEFAULT_AI_RESPONSE_LANGUAGE
                ),
            }
            self._set_busy(True)
            label = ai_preset_info(active["preset"])[1]
            self._status.setText(f"Waiting for {label} ({active['model']})…")
            worker = _OllamaWorker(self, kwargs)
            worker.finished.connect(self._on_ok, Qt.ConnectionType.QueuedConnection)
            worker.failed.connect(self._on_err, Qt.ConnectionType.QueuedConnection)
            worker.cancelled.connect(self._on_cancelled, Qt.ConnectionType.QueuedConnection)
            self._worker = worker
            worker.start()

        def _on_err(self, msg: str) -> None:
            self._append("assistant", f"(Error) {msg}")
            self._status.setText(msg.split("\n", 1)[0][:200])
            low = (msg or "").lower()
            if "http 401" in low or "http 403" in low or "api key required" in low:
                self._auth_forced = True
            self._refresh_auth_chip()
            self._cleanup_worker()

        def _on_cancelled(self) -> None:
            self._status.setText("Stopped.")
            self._cleanup_worker()

        def send_current(self) -> None:
            if self._busy:
                return
            query = self._input.toPlainText().strip()
            if not query:
                return
            cfg = self._settings_dict()
            if str(cfg.get("enabled", "true")).lower() in ("0", "false", "no", "off"):
                self._status.setText("AI is disabled in Settings → AI.")
                return

            ctx: Dict[str, Any] = {}
            if get_context:
                try:
                    ctx = normalize_ai_context(dict(get_context() or {}))
                except Exception as exc:
                    self._status.setText(f"Context error: {exc}")
                    return

            self._input.clear()
            self._send_query(query, ctx)

        def _send_query(self, query: str, ctx: Dict[str, Any]) -> None:
            cfg = self._settings_dict()
            if str(cfg.get("enabled", "true")).lower() in ("0", "false", "no", "off"):
                self._status.setText("AI is disabled in Settings → AI.")
                return

            ctx = normalize_ai_context(ctx)
            self._append("user", query)
            self._tool_round = 0
            self._chat_messages = _build_chat_messages(
                query,
                findings_text=ctx.get("findings_text", ""),
                metrics=ctx.get("metrics"),
                span=ctx.get("span", ""),
                cores=ctx.get("cores", ""),
                scope=ctx.get("scope", ""),
                response_language=cfg.get(
                    "response_language", DEFAULT_AI_RESPONSE_LANGUAGE
                ),
            )
            self._set_busy(True)
            active = resolve_ai_settings(cfg)
            label = ai_preset_info(active["preset"])[1]
            self._status.setText(f"Waiting for {label} ({active['model']})…")

            kwargs = {
                "query": query,
                "messages": list(self._chat_messages),
                "tools": ai_viewer_tools(),
                "base_url": active["base_url"],
                "model": active["model"],
                "api_key": active["api_key"],
                "preset": active["preset"],
                "tls_verify": parse_ai_tls_verify(active.get("tls_verify")),
                "response_language": cfg.get(
                    "response_language", DEFAULT_AI_RESPONSE_LANGUAGE
                ),
            }
            # Worker stays on the GUI thread; only the HTTP call runs off-thread.
            worker = _OllamaWorker(self, kwargs)
            worker.finished.connect(self._on_ok, Qt.ConnectionType.QueuedConnection)
            worker.failed.connect(self._on_err, Qt.ConnectionType.QueuedConnection)
            worker.cancelled.connect(self._on_cancelled, Qt.ConnectionType.QueuedConnection)
            self._worker = worker
            worker.start()

        def _cleanup_worker(self) -> None:
            self._set_busy(False)
            worker = self._worker
            self._worker = None
            if worker is not None:
                try:
                    worker.finished.disconnect(self._on_ok)
                    worker.failed.disconnect(self._on_err)
                    worker.cancelled.disconnect(self._on_cancelled)
                except (TypeError, RuntimeError):
                    pass
                worker.deleteLater()

    return AiAssistantPanel()
