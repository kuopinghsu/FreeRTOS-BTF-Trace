"""Diagnostic assistant for BTF Viewer (any OpenAI-compatible endpoint).

Sends structured Analysis Findings (and optional scoped metrics) to a chat
endpoint — never the raw BTF event stream.
"""
from __future__ import annotations

import json
import os
import re
import threading
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

from ._imports import *  # noqa: F403,F401


class OllamaCancelled(Exception):
    """User stopped an in-flight AI request."""


# Alias used by newer call sites; same exception.
AiCancelled = OllamaCancelled
AI_SYSTEM_PROMPT = (
    "You are an expert Real-Time Operating System (RTOS) and SMP trace analysis "
    "assistant for FreeRTOS BTF traces. Analyse the provided structured metrics "
    "and answer the user's diagnostic question clearly. Focus on root causes "
    "(preemption, priority inversion, lock contention, core thrashing, switch "
    "overhead, tick health). Prefer concrete task names, cores, and durations. "
    "When mentioning a time, write it as jump:TIME where TIME is the numeric "
    "value in the trace time unit (e.g. jump:1805120). Keep answers concise."
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

# Per-preset settings stored in btf_viewer.rc / browser storage.
AI_PRESET_FIELDS: Tuple[str, ...] = ("base_url", "model", "api_key")

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
    return {
        "preset": preset,
        "base_url": str(c.get(f"{preset}_base_url", "") or def_base),
        "model": str(c.get(f"{preset}_model", "") or def_model),
        "api_key": str(c.get(f"{preset}_api_key", "") or ""),
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


def parse_ai_settings_json(data: Any) -> Dict[str, str]:
    """Settings patch from an AI settings JSON file (see ``examples/ai``).

    Accepts a flat file describing one endpoint::

        {"preset": "gemini", "base_url": "…", "model": "…", "api_key": ""}

    or a ``presets`` object carrying several at once. snake_case and camelCase
    key names both work, so files exported from either app import into both.
    Raises ``ValueError`` with a user-facing message when the file cannot be
    applied.
    """
    if isinstance(data, (bytes, bytearray)):
        data = data.decode("utf-8", errors="replace")
    if isinstance(data, str):
        try:
            data = json.loads(data)
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
        entry = {k: v for k, v in entry.items() if v}
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
                or low.startswith("btfjump:")
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
                f'<a href="btfjump:{m.group(1)}" class="ai-jump">'
                f"jump:{m.group(1)}</a>"
            ),
            chunk,
        )
        out_chunks.append(chunk)

    result = "".join(out_chunks)
    for i, frag in enumerate(placeholders):
        result = result.replace(f"\x00MD{i}\x00", frag)
    return result


def markdown_to_safe_html(text: str) -> str:
    """Convert a subset of Markdown to safe HTML (AI reply preview)."""
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

        para.append(stripped)
        i += 1

    _flush_para(para)
    return "".join(out)


def _ai_message_body_html(role: str, text: str) -> str:
    """Message body without the role prefix; assistant replies render as Markdown."""
    body_text = (text or "").strip()
    if role == "assistant":
        return markdown_to_safe_html(body_text) or "<p></p>"
    esc = html.escape(body_text)
    linked = _JUMP_RE.sub(
        lambda m: (
            f'<a href="btfjump:{m.group(1)}" class="ai-jump">'
            f"jump:{m.group(1)}</a>"
        ),
        esc,
    )
    return linked.replace("\n", "<br>")


def _format_ai_log_html(role: str, text: str) -> str:
    """HTML for the conversation log; assistant replies render as Markdown."""
    prefix = "You" if role == "user" else "Assistant"
    body = _ai_message_body_html(role, text)
    if role == "assistant":
        return f"<div class='ai-msg'><p><b>{prefix}:</b></p>{body}</div>"
    return f"<p><b>{prefix}:</b><br>{body}</p>"


def _ai_file_stamp() -> str:
    return datetime.datetime.now().strftime("%Y%m%d-%H%M%S")


def format_ai_conversation_markdown(entries: Sequence[Tuple[str, str]]) -> str:
    """Markdown transcript of the conversation (assistant replies kept as-is)."""
    stamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    out = ["# BTF Viewer — AI Conversation", "", f"_Saved {stamp}_", ""]
    for role, text in entries:
        out.append("## You" if role == "user" else "## Assistant")
        out.append("")
        out.append((text or "").strip())
        out.append("")
    return "\n".join(out).rstrip() + "\n"


def format_ai_conversation_text(entries: Sequence[Tuple[str, str]]) -> str:
    """Plain-text transcript of the conversation."""
    stamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    out = ["BTF Viewer — AI Conversation", f"Saved {stamp}", ""]
    for role, text in entries:
        out.append("You:" if role == "user" else "Assistant:")
        out.append((text or "").strip())
        out.append("")
    return "\n".join(out).rstrip() + "\n"


_AI_HTML_STYLE = """
body{background:#12161d;color:#dbe2ea;font-family:system-ui,-apple-system,'Segoe UI',sans-serif;
  font-size:13px;line-height:1.5;margin:0;padding:20px;}
h1{font-size:18px;margin:0 0 4px;}
.saved{color:#8b98a8;font-size:12px;margin:0 0 16px;}
.msg{border-top:1px solid #2b3442;padding:10px 0;}
.msg h3{font-size:12px;text-transform:uppercase;letter-spacing:.05em;color:#8b98a8;margin:0 0 6px;}
pre{background:#1a2230;border:1px solid #3a4658;border-radius:4px;padding:8px;overflow:auto;}
code{font-family:Menlo,Consolas,Monaco,'Courier New',monospace;font-size:12px;}
blockquote{margin:6px 0;padding:4px 10px;border-left:3px solid #5b9bd5;color:#a8b4c4;}
a{color:#5b9bd5;}
""".strip()


def format_ai_conversation_html(entries: Sequence[Tuple[str, str]]) -> str:
    """Standalone HTML transcript (Markdown rendered, same styling as the panel).

    Keep in sync with aiMarkdown.js::formatAiConversationHtml; Qt's own
    ``toHtml()`` would export editor-flavoured markup instead.
    """
    stamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    parts = []
    for role, text in entries:
        head = "You" if role == "user" else "Assistant"
        cls = "user" if role == "user" else "assistant"
        parts.append(
            f'<section class="msg {cls}"><h3>{head}</h3>'
            f'<div class="body">{_ai_message_body_html(role, text)}</div>'
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
        return " Check API key (Settings → AI, or OPENAI_API_KEY / GEMINI_API_KEY)."
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
    timeout_s: float = 120.0,
    history: Optional[Sequence[Dict[str, str]]] = None,
    cancel_event: Optional[threading.Event] = None,
    on_response: Optional[Callable[[Any], None]] = None,
) -> str:
    """Call OpenAI-compatible ``/chat/completions`` (non-streaming)."""
    url_base = normalize_ai_base_url(base_url)
    url = url_base + "/chat/completions"
    chat_model = (model or DEFAULT_AI_MODEL).strip() or DEFAULT_AI_MODEL
    if cancel_event is not None and cancel_event.is_set():
        raise OllamaCancelled("Stopped")
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
    payload = json.dumps({
        "model": chat_model,
        "messages": messages,
        "stream": False,
    }).encode("utf-8")

    req = urllib.request.Request(
        url,
        data=payload,
        headers=ai_request_headers(api_key, base_url=url_base),
        method="POST",
    )
    try:
        resp = urllib.request.urlopen(req, timeout=timeout_s)
    except urllib.error.HTTPError as exc:
        detail = ""
        try:
            detail = exc.read().decode("utf-8", errors="replace")[:400]
        except Exception:
            pass
        tip = _ai_http_error_tip(exc.code, detail, base_url=url_base)
        raise RuntimeError(
            f"OpenAI-compatible HTTP {exc.code} at {url}: "
            f"{detail or exc.reason}.{tip}"
        ) from exc
    except urllib.error.URLError as exc:
        if cancel_event is not None and cancel_event.is_set():
            raise OllamaCancelled("Stopped") from exc
        raise RuntimeError(
            f"Cannot reach OpenAI-compatible API at {url}.\n{exc.reason}"
        ) from exc
    except TimeoutError as exc:
        raise RuntimeError(
            f"OpenAI-compatible request timed out after {timeout_s:.0f}s ({url})"
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
        body = json.loads(raw)
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

    choices = body.get("choices") if isinstance(body, dict) else None
    if isinstance(choices, list) and choices:
        msg = choices[0].get("message") if isinstance(choices[0], dict) else None
        if isinstance(msg, dict) and msg.get("content"):
            return str(msg["content"]).strip()
    raise RuntimeError(f"Unexpected OpenAI-compatible response: {body!r}"[:500])


def ai_list_models(
    base_url: str = DEFAULT_AI_BASE_URL,
    timeout_s: float = 8.0,
    api_key: str = "",
) -> List[str]:
    """Return model ids from ``GET /models`` on an OpenAI-compatible API."""
    url_base = normalize_ai_base_url(base_url)
    url = url_base + "/models"
    req = urllib.request.Request(
        url, method="GET", headers=ai_request_headers(api_key, base_url=url_base),
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout_s) as resp:
            body = json.loads(resp.read().decode("utf-8"))
    except Exception as exc:
        raise RuntimeError(f"Cannot list models at {url}: {exc}") from exc
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
    timeout_s: float = 60.0,
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
        served = ai_list_models(url_base, timeout_s=min(12.0, timeout_s), api_key=key)
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
    _progress(f"2/2 Chat probe with {model_name}…")
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
        with urllib.request.urlopen(req, timeout=timeout_s) as resp:
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
        raise RuntimeError(f"Chat probe failed at {chat_url}: {exc}") from exc

    reply = ""
    choices = body.get("choices") if isinstance(body, dict) else None
    if isinstance(choices, list) and choices:
        msg = choices[0].get("message") if isinstance(choices[0], dict) else None
        if isinstance(msg, dict):
            reply = str(msg.get("content") or "").strip()
    note = f" Probe reply: {reply[:40]!r}." if reply else ""
    return f"Connected to {url_base}. Model {model_name} ready{listing_note}.{note}"


def create_ai_assistant_panel(
    parent=None,
    *,
    get_context: Optional[Callable[[], Dict[str, Any]]] = None,
    get_settings: Optional[Callable[[], Dict[str, str]]] = None,
    on_open_settings: Optional[Callable[[], None]] = None,
    on_save_settings: Optional[Callable[[Dict[str, str]], None]] = None,
    on_jump: Optional[Callable[[float], None]] = None,
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
                text = ai_chat(
                    **self._kwargs,
                    cancel_event=self._cancel,
                    on_response=self._set_resp,
                )
                if self._cancel.is_set():
                    self.cancelled.emit()
                else:
                    self.finished.emit(text)
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
            self._entries: List[Tuple[str, str]] = []

            root = QVBoxLayout(self)
            root.setContentsMargins(6, 6, 6, 6)
            root.setSpacing(6)

            title = QLabel("AI Assistant")
            title.setStyleSheet("font-weight:600;")
            root.addWidget(title)

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
            self._log.document().setDefaultStyleSheet(
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
            )
            self._log.anchorClicked.connect(self._on_jump_link)
            self._log.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
            self._log.customContextMenuRequested.connect(self._show_log_menu)
            mid_lay.addWidget(self._log, 1)

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

            self._refresh_send_btn()

        def eventFilter(self, obj, event):  # noqa: N802
            if obj is self._input and event.type() == QEvent.Type.KeyPress:
                key = event.key()
                mods = event.modifiers()
                if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter) and (
                    mods & (Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.MetaModifier)
                ):
                    self.send_current()
                    return True
            return QWidget.eventFilter(self, obj, event)

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
            if not on_jump or url.scheme() != "btfjump":
                return
            raw = url.path() or url.toString().split(":", 1)[-1]
            try:
                value = float(raw)
            except ValueError:
                return
            on_jump(value)

        def _append(self, role: str, text: str) -> None:
            self._entries.append((role, text))
            self._log.append(_format_ai_log_html(role, text))
            bar = self._log.verticalScrollBar()
            bar.setValue(bar.maximum())

        def clear_conversation(self) -> None:
            """Clear the conversation log (also stops an in-flight query)."""
            if self._busy:
                self.stop_query()
            self._entries.clear()
            self._log.clear()
            self._status.setText("")

        def _show_log_menu(self, pos) -> None:
            menu = self._log.createStandardContextMenu(pos)
            menu.addSeparator()
            copy_all = menu.addAction("Copy conversation")
            copy_all.setEnabled(bool(self._entries))
            copy_all.triggered.connect(self.copy_conversation)
            save = menu.addAction("Save As…")
            save.setEnabled(bool(self._entries))
            save.triggered.connect(self.save_conversation_as)
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

        def save_conversation_as(self) -> None:
            """Write the conversation to Markdown, plain text or HTML."""
            if not self._entries:
                return
            path, selected = QFileDialog.getSaveFileName(
                self,
                "Save AI Conversation",
                f"ai-conversation-{_ai_file_stamp()}.md",
                "Markdown (*.md);;Text files (*.txt);;HTML (*.html);;All files (*)",
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

        def _use_template(self, template_id: str, prompt: str) -> None:
            if self._busy:
                return
            if template_id == AI_COMPARE_TEMPLATE_ID:
                self._run_compare_template(prompt)
                return
            self._input.setPlainText(prompt)
            self.send_current()

        def _run_compare_template(self, prompt: str) -> None:
            tabs = self._loaded_tabs()
            if len(tabs) < 2:
                self._status.setText("Open at least two BTF tabs to compare.")
                self.refresh_template_availability()
                return
            if len(tabs) == 2:
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

        def _on_ok(self, text: str) -> None:
            self._append("assistant", text)
            jumps = extract_jump_times(text)
            if jumps:
                # Prefer the original token spelling from the reply text.
                token = _JUMP_RE.search(text or "")
                label = token.group(1) if token else f"{jumps[0]:g}"
                self._status.setText(
                    f"Done. Click jump:{label} links to open the timeline."
                )
            else:
                self._status.setText("Done.")
            self._cleanup_worker()

        def _on_err(self, msg: str) -> None:
            self._append("assistant", f"(Error) {msg}")
            self._status.setText(msg.split("\n", 1)[0][:200])
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
            self._set_busy(True)
            active = resolve_ai_settings(cfg)
            label = ai_preset_info(active["preset"])[1]
            self._status.setText(f"Waiting for {label} ({active['model']})…")

            kwargs = {
                "query": query,
                "findings_text": ctx.get("findings_text", ""),
                "metrics": ctx.get("metrics"),
                "span": ctx.get("span", ""),
                "cores": ctx.get("cores", ""),
                "scope": ctx.get("scope", ""),
                "base_url": active["base_url"],
                "model": active["model"],
                "api_key": active["api_key"],
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
