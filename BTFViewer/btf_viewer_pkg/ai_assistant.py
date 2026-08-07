"""Ollama-backed diagnostic assistant for BTF Viewer.

Sends structured Analysis Findings (and optional scoped metrics) to a local
Ollama chat endpoint — never the raw BTF event stream.
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
    """User stopped an in-flight Ollama request."""

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


def normalize_ollama_url(url: str) -> str:
    u = (url or DEFAULT_OLLAMA_URL).strip().rstrip("/")
    # Allow pasting https://ollama.com/api — strip trailing /api.
    if u.lower().endswith("/api"):
        u = u[:-4].rstrip("/")
    return u or DEFAULT_OLLAMA_URL


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
    key = (api_key or "").strip() or os.environ.get("OLLAMA_API_KEY", "").strip()
    if key:
        headers["Authorization"] = f"Bearer {key}"
    return headers


_JUMP_RE = re.compile(r"jump:([0-9]+(?:\.[0-9]+)?)")


def extract_jump_times(text: str) -> List[float]:
    """Parse ``jump:NNNN`` tokens from assistant text (parity with web)."""
    out: List[float] = []
    for m in _JUMP_RE.finditer(text or ""):
        try:
            out.append(float(m.group(1)))
        except ValueError:
            continue
    return out


def _format_ai_log_html(role: str, text: str) -> str:
    """HTML for the conversation log; ``jump:N`` becomes clickable ``btfjump:`` links."""
    prefix = "You" if role == "user" else "Assistant"
    esc = html.escape((text or "").strip())
    linked = _JUMP_RE.sub(
        lambda m: f'<a href="btfjump:{m.group(1)}">jump:{m.group(1)}</a>',
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
):
    """Build the right-panel AI chat widget (requires Qt bindings)."""

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

    class _OllamaWorker(QObject):
        """Runs ollama_chat on a plain Python thread; emits to the GUI thread.

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
            threading.Thread(target=self._run, name="ollama-chat", daemon=True).start()

        def _run(self) -> None:
            try:
                text = ollama_chat(
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
                "Uses Analysis Findings for the current Statistics scope. "
                "Local or cloud Ollama."
            )
            hint.setWordWrap(True)
            hint.setStyleSheet("color:#999;font-size:11px;")
            mid_lay.addWidget(hint)

            tpl_label = QLabel("Templates")
            tpl_label.setStyleSheet("font-weight:600;margin-top:2px;")
            mid_lay.addWidget(tpl_label)

            self._template_btns: List[QPushButton] = []
            for _tid, label, prompt in AI_TEMPLATE_QUESTIONS:
                btn = QPushButton(label)
                btn.setToolTip(prompt)
                btn.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
                btn.clicked.connect(lambda _=False, p=prompt: self._use_template(p))
                mid_lay.addWidget(btn)
                self._template_btns.append(btn)

            self._log = QTextBrowser()
            self._log.setReadOnly(True)
            self._log.setOpenExternalLinks(False)
            self._log.setOpenLinks(False)
            self._log.setPlaceholderText("Conversation appears here…")
            self._log.setMinimumHeight(100)
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
            """Abort the current Ollama request if one is running."""
            if not self._busy:
                return
            self._status.setText("Stopping…")
            worker = self._worker
            if worker is not None:
                worker.cancel()

        def _set_busy(self, busy: bool) -> None:
            self._busy = busy
            self._send_btn.setEnabled(not busy)
            self._stop_btn.setEnabled(busy)
            self._input.setReadOnly(busy)
            for btn in self._template_btns:
                btn.setEnabled(not busy)

        def _use_template(self, prompt: str) -> None:
            if self._busy:
                return
            self._input.setPlainText(prompt)
            self.send_current()

        def _settings_dict(self) -> Dict[str, str]:
            if get_settings:
                return dict(get_settings() or {})
            return {
                "enabled": "true",
                "ollama_url": DEFAULT_OLLAMA_URL,
                "ollama_model": DEFAULT_OLLAMA_MODEL,
                "ollama_api_key": "",
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
                    ctx = dict(get_context() or {})
                except Exception as exc:
                    self._status.setText(f"Context error: {exc}")
                    return

            self._append("user", query)
            self._input.clear()
            self._set_busy(True)
            self._status.setText("Waiting for Ollama…")

            kwargs = {
                "query": query,
                "findings_text": ctx.get("findings_text", ""),
                "metrics": ctx.get("metrics"),
                "span": ctx.get("span", ""),
                "cores": ctx.get("cores", ""),
                "scope": ctx.get("scope", ""),
                "base_url": cfg.get("ollama_url", DEFAULT_OLLAMA_URL),
                "model": cfg.get("ollama_model", DEFAULT_OLLAMA_MODEL),
                "api_key": cfg.get("ollama_api_key", ""),
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
