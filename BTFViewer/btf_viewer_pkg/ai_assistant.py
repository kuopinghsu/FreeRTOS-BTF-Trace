"""Multi-provider diagnostic assistant for BTF Viewer (Ollama + OpenAI-compatible).

Sends structured Analysis Findings (and optional scoped metrics) to a chat
endpoint — never the raw BTF event stream.
"""
from __future__ import annotations

import json
import os
import re
import threading
import urllib.error
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

DEFAULT_OLLAMA_URL = "http://localhost:11434"
DEFAULT_OLLAMA_MODEL = "phi4-mini:3.8b"

# Providers: ollama | openai_compatible
AI_PROVIDER_OLLAMA = "ollama"
AI_PROVIDER_OPENAI = "openai_compatible"
DEFAULT_AI_PROVIDER = AI_PROVIDER_OLLAMA

AI_PROVIDER_CHOICES: Tuple[Tuple[str, str], ...] = (
    (AI_PROVIDER_OLLAMA, "Ollama"),
    (AI_PROVIDER_OPENAI, "OpenAI-compatible"),
)

# OpenAI-compatible presets (id, label, base_url, example_model)
AI_OPENAI_PRESET_CUSTOM = "custom"
AI_OPENAI_PRESETS: Tuple[Tuple[str, str, str, str], ...] = (
    (AI_OPENAI_PRESET_CUSTOM, "Custom", "", ""),
    ("openai", "OpenAI (ChatGPT)", "https://api.openai.com/v1", "gpt-4o-mini"),
    ("xai", "xAI (Grok)", "https://api.x.ai/v1", "grok-3-mini"),
    (
        "gemini",
        "Google Gemini",
        "https://generativelanguage.googleapis.com/v1beta/openai",
        "gemini-3.1-flash-lite",
    ),
    ("deepseek", "DeepSeek", "https://api.deepseek.com/v1", "deepseek-chat"),
)

DEFAULT_OPENAI_PRESET = "openai"
DEFAULT_OPENAI_BASE_URL = "https://api.openai.com/v1"
DEFAULT_OPENAI_MODEL = "gpt-4o-mini"

# Web Vite same-origin proxy path prefix per preset (Desktop ignores these).
AI_OPENAI_PROXY_PATHS: Dict[str, str] = {
    "openai": "/proxy/openai",
    "xai": "/proxy/xai",
    "gemini": "/proxy/gemini",
    "deepseek": "/proxy/deepseek",
}


def normalize_ai_provider(provider: Optional[str]) -> str:
    p = (provider or DEFAULT_AI_PROVIDER).strip().lower().replace("-", "_")
    if p in ("openai", "openai_compat", "openai_compatible", "chatgpt"):
        return AI_PROVIDER_OPENAI
    return AI_PROVIDER_OLLAMA


def openai_preset_info(preset_id: str) -> Tuple[str, str, str, str]:
    """Return (id, label, base_url, example_model) for *preset_id*."""
    want = (preset_id or AI_OPENAI_PRESET_CUSTOM).strip().lower()
    for row in AI_OPENAI_PRESETS:
        if row[0] == want:
            return row
    return AI_OPENAI_PRESETS[0]


def apply_openai_preset(preset_id: str) -> Dict[str, str]:
    """Defaults to apply when the user picks an OpenAI-compatible preset."""
    _id, _label, base, model = openai_preset_info(preset_id)
    out: Dict[str, str] = {"openai_preset": _id}
    if base:
        out["openai_base_url"] = base
    if model:
        out["openai_model"] = model
    return out


def normalize_ollama_url(url: str) -> str:
    u = (url or DEFAULT_OLLAMA_URL).strip().rstrip("/")
    # Allow pasting https://ollama.com/api — strip trailing /api.
    if u.lower().endswith("/api"):
        u = u[:-4].rstrip("/")
    return u or DEFAULT_OLLAMA_URL


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


def normalize_openai_base_url(url: str) -> str:
    """Normalize an OpenAI-compatible API root (…/v1 or vendor equivalent)."""
    u = (url or DEFAULT_OPENAI_BASE_URL).strip().rstrip("/")
    if not u:
        return DEFAULT_OPENAI_BASE_URL
    low = u.lower()
    # Allow pasting the full chat completions URL.
    for suffix in ("/chat/completions", "/completions"):
        if low.endswith(suffix):
            u = u[: -len(suffix)].rstrip("/")
            low = u.lower()
            break
    # Bare api.openai.com → add /v1
    if low in ("https://api.openai.com", "http://api.openai.com"):
        u = u + "/v1"
    elif low in ("https://api.x.ai", "http://api.x.ai"):
        u = u + "/v1"
    elif low in ("https://api.deepseek.com", "http://api.deepseek.com"):
        u = u + "/v1"
    return u


def openai_request_headers(
    api_key: Optional[str] = None,
    *,
    base_url: str = "",
) -> Dict[str, str]:
    """JSON + Bearer from *api_key*, ``OPENAI_API_KEY``, ``GEMINI_API_KEY``, or ``OLLAMA_API_KEY``.

    Gemini OpenAI-compat (``…/v1beta/openai``) must use **only**
    ``Authorization: Bearer`` — also sending ``x-goog-api-key`` causes HTTP 400
    ("Please pass a valid API key" / "Multiple authentication credentials").
    """
    headers = {"Content-Type": "application/json"}
    key = normalize_api_key(api_key)
    if not key:
        key = normalize_api_key(os.environ.get("OPENAI_API_KEY", ""))
    if not key:
        key = normalize_api_key(os.environ.get("GEMINI_API_KEY", ""))
    if not key:
        key = normalize_api_key(os.environ.get("OLLAMA_API_KEY", ""))
    if key:
        headers["Authorization"] = f"Bearer {key}"
    return headers


def is_ollama_cloud_model(name: str) -> bool:
    """True for Ollama cloud tags like ``minimax-m3:cloud`` / ``gpt-oss:20b-cloud``."""
    n = (name or "").strip().lower()
    if not n:
        return False
    return n.endswith(":cloud") or n.endswith("-cloud") or ":cloud" in n


def is_ollama_cloud_host(url: str) -> bool:
    host = normalize_ollama_url(url).lower()
    if "://" in host:
        host = host.split("://", 1)[1]
    host = host.split("/", 1)[0]
    return host == "ollama.com" or host.endswith(".ollama.com")


def resolve_ollama_chat_model(base_url: str, model: str) -> str:
    """Model name for ``/api/chat``.

    Local proxy keeps ``:cloud`` / ``-cloud`` suffixes.
    Direct ``https://ollama.com`` expects the name *without* those suffixes.
    """
    name = (model or DEFAULT_OLLAMA_MODEL).strip() or DEFAULT_OLLAMA_MODEL
    if is_ollama_cloud_host(base_url):
        low = name.lower()
        if low.endswith(":cloud"):
            name = name[: -len(":cloud")]
        elif low.endswith("-cloud"):
            name = name[: -len("-cloud")]
    return name


def ollama_request_headers(api_key: Optional[str] = None) -> Dict[str, str]:
    """JSON headers; add Bearer token from *api_key* or ``OLLAMA_API_KEY``."""
    headers = {"Content-Type": "application/json"}
    key = normalize_api_key(api_key)
    if not key:
        key = normalize_api_key(os.environ.get("OLLAMA_API_KEY", ""))
    if key:
        headers["Authorization"] = f"Bearer {key}"
    return headers


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
            while i < n:
                s = lines[i].strip()
                if ordered:
                    m = re.match(r"^\d+\.\s+(.*)$", s)
                else:
                    m = re.match(r"^[-*+]\s+(.*)$", s)
                if not m:
                    break
                items.append(f"<li>{_md_inline_to_html_escaped(m.group(1))}</li>")
                i += 1
            out.append(f"<{tag}>{''.join(items)}</{tag}>")
            continue

        para.append(stripped)
        i += 1

    _flush_para(para)
    return "".join(out)


def _format_ai_log_html(role: str, text: str) -> str:
    """HTML for the conversation log; assistant replies render as Markdown."""
    prefix = "You" if role == "user" else "Assistant"
    body_text = (text or "").strip()
    if role == "assistant":
        body = markdown_to_safe_html(body_text)
        if not body:
            body = "<p></p>"
        return f"<div class='ai-msg'><p><b>{prefix}:</b></p>{body}</div>"
    esc = html.escape(body_text)
    linked = _JUMP_RE.sub(
        lambda m: (
            f'<a href="btfjump:{m.group(1)}" class="ai-jump">'
            f"jump:{m.group(1)}</a>"
        ),
        esc,
    )
    body = linked.replace("\n", "<br>")
    return f"<p><b>{prefix}:</b><br>{body}</p>"


def _ollama_http_error_message(
    code: int,
    detail: str,
    *,
    url: str,
    model: str,
    base_url: str,
) -> str:
    tip = ""
    if code in (401, 403):
        if is_ollama_cloud_host(base_url) or is_ollama_cloud_model(model):
            tip = (
                " Cloud models need auth: run `ollama signin` (local proxy), "
                "or set an API key for https://ollama.com "
                "(Settings → AI, or OLLAMA_API_KEY)."
            )
        else:
            tip = " Check credentials / API key."
    elif code == 404 and is_ollama_cloud_model(model):
        tip = (
            f" Try `ollama pull {model}` after `ollama signin`, "
            "or use https://ollama.com with an API key "
            f"(model name without :cloud, e.g. {resolve_ollama_chat_model('https://ollama.com', model)!r})."
        )
    body = detail or f"HTTP {code}"
    return f"Ollama HTTP {code} at {url}: {body}.{tip}"


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


def ollama_chat(
    query: str,
    *,
    findings_text: str = "",
    metrics: Optional[Dict[str, Any]] = None,
    span: str = "",
    cores: Any = "",
    scope: str = "",
    base_url: str = DEFAULT_OLLAMA_URL,
    model: str = DEFAULT_OLLAMA_MODEL,
    api_key: str = "",
    response_language: str = DEFAULT_AI_RESPONSE_LANGUAGE,
    timeout_s: float = 120.0,
    history: Optional[Sequence[Dict[str, str]]] = None,
    cancel_event: Optional[threading.Event] = None,
    on_response: Optional[Callable[[Any], None]] = None,
) -> str:
    """Call Ollama ``/api/chat`` (non-streaming) and return assistant text.

    *cancel_event*: when set, abort the HTTP read and raise ``OllamaCancelled``.
    *on_response*: optional callback with the open response (so UI can ``close()`` it).
    """
    url_base = normalize_ollama_url(base_url)
    url = url_base + "/api/chat"
    chat_model = resolve_ollama_chat_model(url_base, model)
    if cancel_event is not None and cancel_event.is_set():
        raise OllamaCancelled("Stopped")
    user_content = build_ai_user_message(
        query,
        findings_text=findings_text,
        metrics=metrics,
        span=span,
        cores=cores,
        scope=scope,
    )
    messages: List[Dict[str, str]] = [
        {"role": "system", "content": build_ai_system_prompt(response_language)},
    ]
    if history:
        for m in history:
            role = m.get("role")
            content = m.get("content")
            if role in ("user", "assistant") and content:
                messages.append({"role": role, "content": str(content)})
    messages.append({"role": "user", "content": user_content})

    payload = json.dumps({
        "model": chat_model,
        "messages": messages,
        "stream": False,
    }).encode("utf-8")

    req = urllib.request.Request(
        url,
        data=payload,
        headers=ollama_request_headers(api_key),
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
        raise RuntimeError(
            _ollama_http_error_message(
                exc.code, detail or str(exc.reason),
                url=url, model=chat_model, base_url=url_base,
            )
        ) from exc
    except urllib.error.URLError as exc:
        if cancel_event is not None and cancel_event.is_set():
            raise OllamaCancelled("Stopped") from exc
        raise RuntimeError(
            f"Cannot reach Ollama at {url}. Is Ollama running?\n{exc.reason}"
        ) from exc
    except TimeoutError as exc:
        raise RuntimeError(
            f"Ollama request timed out after {timeout_s:.0f}s ({url})"
        ) from exc

    if on_response is not None:
        try:
            on_response(resp)
        except Exception:
            pass
    try:
        if cancel_event is not None and cancel_event.is_set():
            raise OllamaCancelled("Stopped")
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
        raw = b"".join(chunks).decode("utf-8")
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

    msg = body.get("message") if isinstance(body, dict) else None
    if isinstance(msg, dict) and msg.get("content"):
        return str(msg["content"]).strip()
    if isinstance(body, dict) and body.get("response"):
        return str(body["response"]).strip()
    raise RuntimeError(f"Unexpected Ollama response: {body!r}"[:500])


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


def _openai_http_error_tip(code: int, detail: str = "", *, base_url: str = "") -> str:
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
                " Try model gemini-3.1-flash-lite (or gemini-3.6-flash). "
                "Older gemini-2.0-* / gemini-2.5-* free quota is often 0 or "
                "closed to new users — enable billing or switch model/project."
            )
        return tip
    if code == 404:
        tip = " Check Base URL and model name for this provider."
        if "no longer available" in low or "not found" in low:
            tip += (
                " For Gemini, try gemini-3.1-flash-lite or gemini-3.6-flash "
                "(gemini-2.5-* is closed to many new accounts)."
            )
        return tip
    return ""


def openai_compatible_chat(
    query: str,
    *,
    findings_text: str = "",
    metrics: Optional[Dict[str, Any]] = None,
    span: str = "",
    cores: Any = "",
    scope: str = "",
    base_url: str = DEFAULT_OPENAI_BASE_URL,
    model: str = DEFAULT_OPENAI_MODEL,
    api_key: str = "",
    response_language: str = DEFAULT_AI_RESPONSE_LANGUAGE,
    timeout_s: float = 120.0,
    history: Optional[Sequence[Dict[str, str]]] = None,
    cancel_event: Optional[threading.Event] = None,
    on_response: Optional[Callable[[Any], None]] = None,
) -> str:
    """Call OpenAI-compatible ``/chat/completions`` (non-streaming)."""
    url_base = normalize_openai_base_url(base_url)
    url = url_base + "/chat/completions"
    chat_model = (model or DEFAULT_OPENAI_MODEL).strip() or DEFAULT_OPENAI_MODEL
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
        headers=openai_request_headers(api_key, base_url=url_base),
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
        tip = _openai_http_error_tip(exc.code, detail, base_url=url_base)
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


def ai_chat(
    query: str,
    *,
    provider: str = DEFAULT_AI_PROVIDER,
    findings_text: str = "",
    metrics: Optional[Dict[str, Any]] = None,
    span: str = "",
    cores: Any = "",
    scope: str = "",
    base_url: str = "",
    model: str = "",
    api_key: str = "",
    response_language: str = DEFAULT_AI_RESPONSE_LANGUAGE,
    timeout_s: float = 120.0,
    history: Optional[Sequence[Dict[str, str]]] = None,
    cancel_event: Optional[threading.Event] = None,
    on_response: Optional[Callable[[Any], None]] = None,
) -> str:
    """Dispatch to Ollama or OpenAI-compatible chat."""
    prov = normalize_ai_provider(provider)
    if prov == AI_PROVIDER_OPENAI:
        return openai_compatible_chat(
            query,
            findings_text=findings_text,
            metrics=metrics,
            span=span,
            cores=cores,
            scope=scope,
            base_url=base_url or DEFAULT_OPENAI_BASE_URL,
            model=model or DEFAULT_OPENAI_MODEL,
            api_key=api_key,
            response_language=response_language,
            timeout_s=timeout_s,
            history=history,
            cancel_event=cancel_event,
            on_response=on_response,
        )
    return ollama_chat(
        query,
        findings_text=findings_text,
        metrics=metrics,
        span=span,
        cores=cores,
        scope=scope,
        base_url=base_url or DEFAULT_OLLAMA_URL,
        model=model or DEFAULT_OLLAMA_MODEL,
        api_key=api_key,
        response_language=response_language,
        timeout_s=timeout_s,
        history=history,
        cancel_event=cancel_event,
        on_response=on_response,
    )


def openai_compatible_test_connection(
    base_url: str = DEFAULT_OPENAI_BASE_URL,
    model: str = DEFAULT_OPENAI_MODEL,
    *,
    api_key: str = "",
    timeout_s: float = 60.0,
    on_progress: Optional[Callable[[str], None]] = None,
) -> str:
    """Tiny chat probe against an OpenAI-compatible endpoint."""
    def _progress(msg: str) -> None:
        if on_progress is not None:
            try:
                on_progress(msg)
            except Exception:
                pass

    url_base = normalize_openai_base_url(base_url)
    model_name = (model or DEFAULT_OPENAI_MODEL).strip() or DEFAULT_OPENAI_MODEL
    key = normalize_api_key(api_key)
    if not key:
        key = normalize_api_key(os.environ.get("OPENAI_API_KEY", ""))
    if not key:
        key = normalize_api_key(os.environ.get("GEMINI_API_KEY", ""))
    if not key:
        key = normalize_api_key(os.environ.get("OLLAMA_API_KEY", ""))
    if not key:
        raise RuntimeError(
            "API key required for OpenAI-compatible providers "
            "(Settings → AI → API key, or OPENAI_API_KEY / GEMINI_API_KEY). "
            "Paste the raw key only — no Bearer prefix."
        )
    chat_url = url_base + "/chat/completions"
    _progress(f"1/2 Contacting {url_base}…")
    _progress(
        f"2/2 Chat probe with {model_name} "
        f"(API key length {len(key)})…"
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
        headers=openai_request_headers(key, base_url=url_base),
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
        tip = _openai_http_error_tip(exc.code, detail, base_url=url_base)
        raise RuntimeError(
            f"OpenAI-compatible HTTP {exc.code} at {chat_url}: "
            f"{detail or exc.reason}.{tip}"
        ) from exc
    except Exception as exc:
        raise RuntimeError(
            f"OpenAI-compatible chat probe failed at {chat_url}: {exc}"
        ) from exc

    reply = ""
    choices = body.get("choices") if isinstance(body, dict) else None
    if isinstance(choices, list) and choices:
        msg = choices[0].get("message") if isinstance(choices[0], dict) else None
        if isinstance(msg, dict):
            reply = str(msg.get("content") or "").strip()
    note = f" Probe reply: {reply[:40]!r}." if reply else ""
    return f"Connected to {url_base}. Model {model_name} ready.{note}"


def ai_test_connection(
    *,
    provider: str = DEFAULT_AI_PROVIDER,
    base_url: str = "",
    model: str = "",
    api_key: str = "",
    timeout_s: float = 60.0,
    probe_chat: bool = True,
    on_progress: Optional[Callable[[str], None]] = None,
) -> str:
    """Verify the active AI provider (Ollama or OpenAI-compatible)."""
    if normalize_ai_provider(provider) == AI_PROVIDER_OPENAI:
        return openai_compatible_test_connection(
            base_url or DEFAULT_OPENAI_BASE_URL,
            model or DEFAULT_OPENAI_MODEL,
            api_key=api_key,
            timeout_s=timeout_s,
            on_progress=on_progress,
        )
    return ollama_test_connection(
        base_url or DEFAULT_OLLAMA_URL,
        model or DEFAULT_OLLAMA_MODEL,
        api_key=api_key,
        timeout_s=timeout_s,
        probe_chat=probe_chat,
        on_progress=on_progress,
    )


def ollama_list_models(
    base_url: str = DEFAULT_OLLAMA_URL,
    timeout_s: float = 8.0,
    api_key: str = "",
) -> List[str]:
    """Return installed model names from ``GET /api/tags``."""
    url_base = normalize_ollama_url(base_url)
    url = url_base + "/api/tags"
    req = urllib.request.Request(
        url, method="GET", headers=ollama_request_headers(api_key),
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout_s) as resp:
            body = json.loads(resp.read().decode("utf-8"))
    except Exception as exc:
        raise RuntimeError(f"Cannot list Ollama models at {url}: {exc}") from exc
    models = []
    for m in (body.get("models") or []) if isinstance(body, dict) else []:
        name = m.get("name") if isinstance(m, dict) else None
        if name:
            models.append(str(name))
    return models


def match_ollama_model(requested: str, installed: Sequence[str]) -> Optional[str]:
    """Return the best installed name matching *requested*, or None."""
    want = (requested or "").strip()
    if not want:
        return None
    names = [str(n) for n in installed if n]
    if want in names:
        return want

    def _cloud_base(n: str) -> str:
        low = n.lower()
        if low.endswith(":cloud"):
            return n[: -len(":cloud")]
        if low.endswith("-cloud"):
            return n[: -len("-cloud")]
        return n

    # Ollama may report "name:tag" while the user typed "name" or vice versa.
    want_base = want.split(":", 1)[0]
    want_cloud_base = _cloud_base(want).lower()
    for n in names:
        if n == want or n.startswith(want + ":") or n.split(":", 1)[0] == want:
            return n
        if n.split(":", 1)[0] == want_base and ":" not in want:
            return n
        if is_ollama_cloud_model(want) or is_ollama_cloud_model(n):
            if _cloud_base(n).lower() == want_cloud_base:
                if is_ollama_cloud_model(want):
                    # Prefer a cloud-tagged listing when the user asked for cloud.
                    if is_ollama_cloud_model(n):
                        return n
                    continue
                return n
    if is_ollama_cloud_model(want):
        for n in names:
            if is_ollama_cloud_model(n) and _cloud_base(n).lower() == want_cloud_base:
                return n
            if n.split(":", 1)[0].lower() == want_base.lower() and is_ollama_cloud_model(n):
                return n
    return None


def ollama_test_connection(
    base_url: str = DEFAULT_OLLAMA_URL,
    model: str = DEFAULT_OLLAMA_MODEL,
    *,
    api_key: str = "",
    timeout_s: float = 60.0,
    probe_chat: bool = True,
    on_progress: Optional[Callable[[str], None]] = None,
) -> str:
    """Verify Ollama is reachable and *model* is usable.

    1. ``GET /api/tags`` — server up, list installed models
    2. Confirm *model* is among them (flexible name match). Cloud models
       (``*:cloud``) may be absent from tags until pulled — those still proceed
       to a chat probe.
    3. Optional tiny ``/api/chat`` probe so the model actually loads

    *on_progress* is called with short status strings between steps
    (useful for UI feedback while a large model loads).
    """
    def _progress(msg: str) -> None:
        if on_progress is not None:
            try:
                on_progress(msg)
            except Exception:
                pass

    url_base = normalize_ollama_url(base_url)
    model_name = (model or DEFAULT_OLLAMA_MODEL).strip() or DEFAULT_OLLAMA_MODEL
    cloudish = is_ollama_cloud_model(model_name) or is_ollama_cloud_host(url_base)

    _progress(f"1/3 Contacting Ollama at {url_base}…")
    try:
        installed = ollama_list_models(
            url_base, timeout_s=min(12.0, timeout_s), api_key=api_key,
        )
    except RuntimeError:
        raise
    except Exception as exc:
        raise RuntimeError(f"Cannot reach Ollama at {url_base}: {exc}") from exc

    _progress(f"2/3 Checking model {model_name!r}…")
    matched = match_ollama_model(model_name, installed)
    if matched is None:
        if cloudish:
            matched = resolve_ollama_chat_model(url_base, model_name)
            _progress(
                f"2/3 Cloud model {matched!r} not in local tags — "
                f"will probe chat (need `ollama signin` / API key)…"
            )
        else:
            listing = ", ".join(installed[:12]) if installed else "(none)"
            more = f" … +{len(installed) - 12} more" if len(installed) > 12 else ""
            raise RuntimeError(
                f"Model {model_name!r} is not installed at {url_base}. "
                f"Installed: {listing}{more}. "
                f"Try: ollama pull {model_name}"
            )

    chat_model = resolve_ollama_chat_model(url_base, matched if matched else model_name)
    # Keep cloud suffix for local proxy when the user typed it / tags had it.
    if not is_ollama_cloud_host(url_base) and matched:
        chat_model = matched

    if probe_chat:
        _progress(
            f"3/3 Running chat probe with {chat_model} "
            f"(cloud / first load can take a while)…"
        )
        chat_url = url_base + "/api/chat"
        payload = json.dumps({
            "model": chat_model,
            "stream": False,
            "messages": [{"role": "user", "content": "Reply with exactly: OK"}],
            "options": {"num_predict": 8},
        }).encode("utf-8")
        req = urllib.request.Request(
            chat_url,
            data=payload,
            headers=ollama_request_headers(api_key),
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
            raise RuntimeError(
                _ollama_http_error_message(
                    exc.code, detail or str(exc.reason),
                    url=chat_url, model=chat_model, base_url=url_base,
                )
            ) from exc
        except Exception as exc:
            raise RuntimeError(
                f"Ollama reached, model {chat_model!r} listed/allowed, "
                f"but chat probe failed: {exc}"
            ) from exc
        msg = body.get("message") if isinstance(body, dict) else None
        reply = ""
        if isinstance(msg, dict):
            reply = str(msg.get("content") or "").strip()
        elif isinstance(body, dict):
            reply = str(body.get("response") or "").strip()
        note = f" Probe reply: {reply[:40]!r}." if reply else ""
        cloud_note = " (cloud)" if cloudish else ""
        return (
            f"Connected to {url_base}. Model {chat_model}{cloud_note} ready "
            f"({len(installed)} listed).{note}"
        )

    return (
        f"Connected to {url_base}. Model {chat_model} is available "
        f"({len(installed)} models listed)."
    )


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
                "Ask", "Send the question below (Ctrl+Enter)", primary=True)
            self._send_btn.clicked.connect(self.send_current)
            row1.addWidget(self._send_btn)
            self._lang_btn = _ai_action_btn(
                "Language…", "Preferred language for assistant replies")
            self._lang_btn.clicked.connect(self._choose_language)
            row1.addWidget(self._lang_btn)
            self._settings_btn = _ai_action_btn(
                "Settings…", "Configure Ollama URL and model")
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
                "Configure provider in Settings → AI."
            )
            hint.setWordWrap(True)
            hint.setStyleSheet("color:#999;font-size:11px;")
            mid_lay.addWidget(hint)

            tpl_label = QLabel("Templates")
            tpl_label.setStyleSheet("font-weight:600;margin-top:2px;")
            mid_lay.addWidget(tpl_label)

            self._template_btns: List[QPushButton] = []
            self._compare_btn: Optional[QPushButton] = None
            for _tid, label, prompt in AI_TEMPLATE_QUESTIONS:
                btn = QPushButton(label)
                btn.setToolTip(prompt)
                btn.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
                btn.clicked.connect(
                    lambda _=False, t=_tid, p=prompt: self._use_template(t, p)
                )
                mid_lay.addWidget(btn)
                self._template_btns.append(btn)
                if _tid == AI_COMPARE_TEMPLATE_ID:
                    self._compare_btn = btn

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
            mid_lay.addWidget(self._log, 1)

            mid_scroll.setWidget(mid)
            root.addWidget(mid_scroll, 1)

            self._input = QPlainTextEdit()
            self._input.setPlaceholderText("Ask about this trace… (Ctrl+Enter to send)")
            self._input.setFixedHeight(64)
            self._input.installEventFilter(self)
            root.addWidget(self._input)

            self._status = QLabel("")
            self._status.setStyleSheet("color:#999;font-size:11px;")
            self._status.setWordWrap(True)
            root.addWidget(self._status)

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
            self._log.append(_format_ai_log_html(role, text))
            bar = self._log.verticalScrollBar()
            bar.setValue(bar.maximum())

        def clear_conversation(self) -> None:
            """Clear the conversation log (also stops an in-flight query)."""
            if self._busy:
                self.stop_query()
            self._log.clear()
            self._status.setText("")

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

        def _set_busy(self, busy: bool) -> None:
            self._busy = busy
            enabled = self._ai_is_enabled()
            self._send_btn.setEnabled((not busy) and enabled)
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
                "provider": DEFAULT_AI_PROVIDER,
                "ollama_url": DEFAULT_OLLAMA_URL,
                "ollama_model": DEFAULT_OLLAMA_MODEL,
                "ollama_api_key": "",
                "openai_preset": DEFAULT_OPENAI_PRESET,
                "openai_base_url": DEFAULT_OPENAI_BASE_URL,
                "openai_model": DEFAULT_OPENAI_MODEL,
                "openai_api_key": "",
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
            provider = normalize_ai_provider(cfg.get("provider", DEFAULT_AI_PROVIDER))
            waiting = (
                "Waiting for OpenAI-compatible API…"
                if provider == AI_PROVIDER_OPENAI
                else "Waiting for Ollama…"
            )
            self._status.setText(waiting)

            if provider == AI_PROVIDER_OPENAI:
                base_url = cfg.get("openai_base_url", DEFAULT_OPENAI_BASE_URL)
                model = cfg.get("openai_model", DEFAULT_OPENAI_MODEL)
                api_key = cfg.get("openai_api_key", "")
            else:
                base_url = cfg.get("ollama_url", DEFAULT_OLLAMA_URL)
                model = cfg.get("ollama_model", DEFAULT_OLLAMA_MODEL)
                api_key = cfg.get("ollama_api_key", "")

            kwargs = {
                "query": query,
                "provider": provider,
                "findings_text": ctx.get("findings_text", ""),
                "metrics": ctx.get("metrics"),
                "span": ctx.get("span", ""),
                "cores": ctx.get("cores", ""),
                "scope": ctx.get("scope", ""),
                "base_url": base_url,
                "model": model,
                "api_key": api_key,
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
