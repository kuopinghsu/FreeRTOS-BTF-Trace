"""Viewer tool-calling schema for the AI Assistant (Desktop + Web).

OpenAI / Ollama / Gemini OpenAI-compat ``tools`` definitions. Keep in sync
with ``web/src/utils/aiTools.js``.
"""
from __future__ import annotations

import csv
import io
import json
import re
import urllib.parse
from typing import Any, Dict, List, Optional, Sequence, Tuple

AI_TOOL_SET_CURSORS = "set_cursors"
AI_TOOL_ZOOM_TO_RANGE = "zoom_to_range"
AI_TOOL_HIGHLIGHT_TASK = "highlight_task"
AI_TOOL_SET_VIEW_MODE = "set_view_mode"
AI_TOOL_OPEN_CORRIDOR = "open_corridor_inspector"
AI_TOOL_ADD_ANNOTATION = "add_annotation"
AI_TOOL_QUERY_RAW_METRIC = "query_raw_metric"
AI_TOOL_EXPORT_REPORT = "export_report"

AI_VIEWER_TOOL_NAMES: Tuple[str, ...] = (
    AI_TOOL_SET_CURSORS,
    AI_TOOL_ZOOM_TO_RANGE,
    AI_TOOL_HIGHLIGHT_TASK,
    AI_TOOL_SET_VIEW_MODE,
    AI_TOOL_OPEN_CORRIDOR,
    AI_TOOL_ADD_ANNOTATION,
    AI_TOOL_QUERY_RAW_METRIC,
    AI_TOOL_EXPORT_REPORT,
)

AI_RAW_METRIC_PRIORITY = "priority_inheritance"
AI_RAW_METRIC_EXECUTION = "execution"
AI_RAW_METRIC_MIGRATIONS = "migrations"
AI_RAW_METRIC_BLOCKING = "blocking"
AI_RAW_METRIC_SYNC = "sync"
AI_RAW_METRIC_FINDINGS = "findings"
AI_RAW_METRIC_NAMES: Tuple[str, ...] = (
    AI_RAW_METRIC_PRIORITY,
    AI_RAW_METRIC_EXECUTION,
    AI_RAW_METRIC_MIGRATIONS,
    AI_RAW_METRIC_BLOCKING,
    AI_RAW_METRIC_SYNC,
    AI_RAW_METRIC_FINDINGS,
)
_RAW_METRIC_ALIASES = {
    "priority_inheritance": AI_RAW_METRIC_PRIORITY,
    "priority": AI_RAW_METRIC_PRIORITY,
    "pi": AI_RAW_METRIC_PRIORITY,
    "inversion": AI_RAW_METRIC_PRIORITY,
    "inherit": AI_RAW_METRIC_PRIORITY,
    "execution": AI_RAW_METRIC_EXECUTION,
    "wcet": AI_RAW_METRIC_EXECUTION,
    "cpu": AI_RAW_METRIC_EXECUTION,
    "slices": AI_RAW_METRIC_EXECUTION,
    "run": AI_RAW_METRIC_EXECUTION,
    "migrations": AI_RAW_METRIC_MIGRATIONS,
    "migration": AI_RAW_METRIC_MIGRATIONS,
    "migr": AI_RAW_METRIC_MIGRATIONS,
    "thrash": AI_RAW_METRIC_MIGRATIONS,
    "blocking": AI_RAW_METRIC_BLOCKING,
    "block": AI_RAW_METRIC_BLOCKING,
    "wait": AI_RAW_METRIC_BLOCKING,
    "latency": AI_RAW_METRIC_BLOCKING,
    "sync": AI_RAW_METRIC_SYNC,
    "mutex": AI_RAW_METRIC_SYNC,
    "semaphore": AI_RAW_METRIC_SYNC,
    "lock": AI_RAW_METRIC_SYNC,
    "findings": AI_RAW_METRIC_FINDINGS,
    "finding": AI_RAW_METRIC_FINDINGS,
    "analysis": AI_RAW_METRIC_FINDINGS,
}
_MAX_RAW_METRIC_ROWS = 40
_MAX_ANNOTATION_NOTE = 240

# QTextBrowser truncates ``scheme:digits`` (treats it as host:port). Use a path.
_BTF_JUMP_HREF_RE = re.compile(
    r"btfjump:(?://)?(?:time/)?([0-9]+(?:\.[0-9]+)?)",
    re.IGNORECASE,
)
_BTF_HIGHLIGHT_HREF_RE = re.compile(
    r"btfhighlight:(?://)?(?:task/)?(.+)$",
    re.IGNORECASE,
)


def btf_jump_href(value: Any) -> str:
    """Chat href for ``jump:TIME`` that survives QTextBrowser ``setHtml``."""
    try:
        n = float(value)
    except (TypeError, ValueError):
        return "btfjump:time/0"
    token = str(int(n)) if n.is_integer() else str(n)
    return f"btfjump:time/{token}"


def parse_btf_jump_href(href: Any) -> Optional[float]:
    """Parse ``btfjump:time/N`` or legacy ``btfjump:N``."""
    m = _BTF_JUMP_HREF_RE.search(str(href or ""))
    if not m:
        return None
    try:
        return float(m.group(1))
    except (TypeError, ValueError):
        return None


def btf_highlight_href(name: str) -> str:
    """Chat href for a highlight target (slash form + percent-encoding)."""
    token = urllib.parse.quote(str(name or "").strip(), safe="")
    return f"btfhighlight:task/{token}"


def parse_btf_highlight_href(href: Any) -> str:
    """Parse ``btfhighlight:task/…`` or legacy ``btfhighlight:Name``."""
    m = _BTF_HIGHLIGHT_HREF_RE.search(str(href or "").strip())
    if not m:
        return ""
    return urllib.parse.unquote(m.group(1).strip().lstrip("/"))

# Appended to the base system prompt. Keep in sync with web aiTools.js.
AI_TOOL_SYSTEM_ADDENDUM = (
    "When the user asks to show, focus, inspect, zoom, highlight, annotate, "
    "export, or jump to a time range, task, or core pair, you MUST invoke the "
    "matching viewer tool (native function call) in addition to your markdown "
    "answer. Valid tools: set_cursors, zoom_to_range, highlight_task, "
    "set_view_mode, open_corridor_inspector, add_annotation, query_raw_metric, "
    "export_report. Use query_raw_metric when you need the exact per-task "
    "series (priority-inheritance episodes, execution slices, migrations, "
    "blocking gaps, sync STI, or findings lines) instead of the summarised "
    "findings card. Use add_annotation to pin a note on a spike. Use "
    "export_report to save findings, diagrams, and GUI state as HTML or CSV. "
    "Tool timestamps use the same numeric trace time "
    "unit as jump:TIME. After tools run, summarise what you changed. "
    "If you cannot emit a native function call, emit one fenced btftool JSON "
    "object per action, for example:\n"
    "```btftool\n"
    '{"name": "set_cursors", "arguments": {"timestamps": [1805120, 1810000]}}\n'
    "```\n"
    "When a mutex take/give, block, resume, or priority-boost sequence is the point, "
    "include a fenced mermaid sequenceDiagram. When summarising core-to-core "
    "migrations, include a fenced mermaid graph LR flowchart with cores as nodes "
    "and migration counts on edges."
)

AI_MERMAID_SEQUENCE_EXAMPLE = """```mermaid
sequenceDiagram
  autonumber
  participant L as Low[266] (Core 0)
  participant M as Med[267] (Core 0)
  participant H as High[268] (Core 0)
  L->>Mutex(0x80018700): take
  M->>Core 0: runs work
  H->>Mutex(0x80018700): take (Blocked)
  Note over L: Kernel boosts Low -> Pri 4
  L->>Mutex(0x80018700): give
  H->>Mutex(0x80018700): acquires lock
```"""

AI_MERMAID_MIGRATION_EXAMPLE = """```mermaid
graph LR
  C0[Core_0] -->|12| C1[Core_1]
  C1 -->|3| C0
```"""

_MAX_CURSORS_TOOL = 8
_MAX_TOOL_ROUNDS = 4


def ai_viewer_tools() -> List[Dict[str, Any]]:
    """OpenAI-compatible ``tools`` array."""
    return [
        {
            "type": "function",
            "function": {
                "name": AI_TOOL_SET_CURSORS,
                "description": (
                    "Clear existing cursors and place new ones at the given "
                    "trace timestamps. Enables Limit to C1–Cn statistics when "
                    "two or more cursors are placed."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "timestamps": {
                            "type": "array",
                            "items": {"type": "number"},
                            "description": (
                                "Trace time-unit timestamps (same unit as jump:TIME), "
                                "earliest to latest. 1–8 values."
                            ),
                        },
                    },
                    "required": ["timestamps"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": AI_TOOL_ZOOM_TO_RANGE,
                "description": "Zoom and pan the timeline so start_time..end_time fills the view.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "start_time": {
                            "type": "number",
                            "description": "Range start in trace time units.",
                        },
                        "end_time": {
                            "type": "number",
                            "description": "Range end in trace time units.",
                        },
                    },
                    "required": ["start_time", "end_time"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": AI_TOOL_HIGHLIGHT_TASK,
                "description": (
                    "Lock-highlight a task on the timeline (Task View). "
                    "Pass empty string to clear the highlight."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "task_name_or_id": {
                            "type": "string",
                            "description": (
                                "Task display name (e.g. Low[266]), merge key, "
                                "or numeric task id."
                            ),
                        },
                    },
                    "required": ["task_name_or_id"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": AI_TOOL_SET_VIEW_MODE,
                "description": "Switch Task View vs Core View and optional timeline orientation.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "mode": {
                            "type": "string",
                            "enum": ["task", "core"],
                            "description": "task = one row per task; core = one row per core.",
                        },
                        "orientation": {
                            "type": "string",
                            "enum": ["horizontal", "vertical"],
                            "description": "Optional layout orientation.",
                        },
                    },
                    "required": ["mode"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": AI_TOOL_OPEN_CORRIDOR,
                "description": (
                    "Open the Migration & Corridor Inspector. Optionally focus a "
                    "directed core pair (e.g. Core_0 → Core_1)."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "core_from": {
                            "type": "string",
                            "description": "Source core name (e.g. Core_0).",
                        },
                        "core_to": {
                            "type": "string",
                            "description": "Destination core name (e.g. Core_1).",
                        },
                    },
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": AI_TOOL_ADD_ANNOTATION,
                "description": (
                    "Place an orange timeline annotation at a timestamp "
                    "(same unit as jump:TIME) and jump there. Use this to mark "
                    "anomalous spikes, inversion windows, or other points of interest."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "time": {
                            "type": "number",
                            "description": "Trace time-unit timestamp.",
                        },
                        "note": {
                            "type": "string",
                            "description": "Short annotation label shown on the Marks panel.",
                        },
                    },
                    "required": ["time", "note"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": AI_TOOL_QUERY_RAW_METRIC,
                "description": (
                    "Read the underlying per-task metric series for the current "
                    "Statistics scope (cursor range when Limit to C1–Cn is on). "
                    "Returns JSON samples — not a GUI change. Metrics: "
                    "priority_inheritance, execution, migrations, blocking, "
                    "sync, findings."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "task": {
                            "type": "string",
                            "description": (
                                "Task display name (e.g. Low[266]), merge key, "
                                "or numeric task id."
                            ),
                        },
                        "metric": {
                            "type": "string",
                            "enum": list(AI_RAW_METRIC_NAMES),
                            "description": "Which series to return.",
                        },
                    },
                    "required": ["task", "metric"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": AI_TOOL_EXPORT_REPORT,
                "description": (
                    "Download a report bundling Analysis Findings, the AI "
                    "conversation (including mermaid diagrams), annotations, "
                    "and the current GUI state (cursors, highlight, view)."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "format": {
                            "type": "string",
                            "enum": ["html", "csv"],
                            "description": "html (default) or csv.",
                        },
                    },
                },
            },
        },
    ]


def parse_tool_arguments(raw: Any) -> Dict[str, Any]:
    """Parse a tool ``arguments`` field (JSON string or already a dict)."""
    if raw is None:
        return {}
    if isinstance(raw, dict):
        return dict(raw)
    text = str(raw).strip()
    if not text:
        return {}
    try:
        data = json.loads(text)
    except (TypeError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def message_content_text(content: Any) -> str:
    """Flatten OpenAI / Gemini ``content`` (string or parts list) to text."""
    if content is None:
        return ""
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        parts: List[str] = []
        for item in content:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict):
                if item.get("type") in ("text", "output_text", None) or "text" in item:
                    parts.append(str(item.get("text") or item.get("content") or ""))
        return "\n".join(p for p in parts if p).strip()
    return str(content).strip()


# Gemini 3 OpenAI-compat requires thought_signature on the first functionCall
# of each step. Echo the real blob; use this dummy only when the call was not
# produced by Gemini (https://ai.google.dev/gemini-api/docs/thought-signatures).
GEMINI_SKIP_THOUGHT_SIGNATURE = "skip_thought_signature_validator"


def thought_signature_from_obj(obj: Any) -> str:
    """Read a Gemini thought signature from a tool_call / message / part."""
    if not isinstance(obj, dict):
        return ""
    for key in ("thought_signature", "thoughtSignature"):
        val = obj.get(key)
        if isinstance(val, str) and val.strip():
            return val.strip()
    extra = obj.get("extra_content")
    if isinstance(extra, dict):
        google = extra.get("google") if isinstance(extra.get("google"), dict) else {}
        for src in (google, extra):
            for key in ("thought_signature", "thoughtSignature"):
                val = src.get(key)
                if isinstance(val, str) and val.strip():
                    return val.strip()
    fn = obj.get("function")
    if isinstance(fn, dict):
        for key in ("thought_signature", "thoughtSignature"):
            val = fn.get(key)
            if isinstance(val, str) and val.strip():
                return val.strip()
    return ""


def gemini_thought_extra_content(signature: str) -> Dict[str, Any]:
    return {"google": {"thought_signature": str(signature)}}


def attach_thought_signature(call: Dict[str, Any], signature: str) -> Dict[str, Any]:
    """Set ``extra_content.google.thought_signature`` on an OpenAI-shaped call."""
    sig = str(signature or "").strip()
    if not sig:
        return call
    extra = call.get("extra_content")
    extra = dict(extra) if isinstance(extra, dict) else {}
    google = extra.get("google")
    google = dict(google) if isinstance(google, dict) else {}
    google["thought_signature"] = sig
    extra["google"] = google
    call["extra_content"] = extra
    return call


def needs_gemini_thought_signatures(
    *,
    base_url: str = "",
    model: str = "",
    preset: str = "",
) -> bool:
    """True for Gemini OpenAI-compat hosts / the Gemini preset."""
    del model  # model id alone is not enough (Ollama can serve gemini-* names)
    blob = f"{base_url} {preset}".lower()
    return "generativelanguage" in blob or "gemini" in blob


def ensure_gemini_thought_signatures(
    messages: Sequence[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """First function call in each assistant step must carry a thought_signature."""
    out: List[Dict[str, Any]] = []
    for msg in messages or []:
        if not isinstance(msg, dict):
            continue
        if str(msg.get("role") or "") != "assistant":
            out.append(msg)
            continue
        calls = msg.get("tool_calls")
        if not isinstance(calls, list) or not calls:
            out.append(msg)
            continue
        copied = dict(msg)
        new_calls: List[Any] = []
        for i, call in enumerate(calls):
            if not isinstance(call, dict):
                new_calls.append(call)
                continue
            c = dict(call)
            fn = c.get("function")
            if isinstance(fn, dict):
                c["function"] = dict(fn)
            sig = thought_signature_from_obj(c)
            if i == 0 and not sig:
                sig = GEMINI_SKIP_THOUGHT_SIGNATURE
            if sig:
                attach_thought_signature(c, sig)
            new_calls.append(c)
        copied["tool_calls"] = new_calls
        out.append(copied)
    return out


def _extracted_tool_call(
    *,
    cid: str,
    name: str,
    arguments: Dict[str, Any],
    signature: str = "",
) -> Dict[str, Any]:
    item: Dict[str, Any] = {"id": cid, "name": name, "arguments": arguments}
    if signature:
        item["thought_signature"] = signature
    return item


def extract_tool_calls(message: Optional[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Normalise OpenAI / Ollama / Gemini / legacy function_call invocations."""
    if not isinstance(message, dict):
        return []
    out: List[Dict[str, Any]] = []
    calls = message.get("tool_calls")
    if isinstance(calls, str):
        try:
            calls = json.loads(calls)
        except (TypeError, ValueError):
            calls = []
    if isinstance(calls, list):
        for i, call in enumerate(calls):
            if not isinstance(call, dict):
                continue
            fn = call.get("function") if isinstance(call.get("function"), dict) else {}
            name = str(
                fn.get("name") or call.get("name") or call.get("tool") or ""
            ).strip()
            if not name:
                continue
            args = parse_tool_arguments(
                fn.get("arguments",
                       call.get("arguments", call.get("args", call.get("input"))))
            )
            cid = str(call.get("id") or f"call_{i}")
            out.append(_extracted_tool_call(
                cid=cid,
                name=name,
                arguments=args,
                signature=thought_signature_from_obj(call),
            ))
    legacy = message.get("function_call")
    if isinstance(legacy, dict) and legacy.get("name"):
        out.append(_extracted_tool_call(
            cid=str(legacy.get("id") or "call_0"),
            name=str(legacy["name"]).strip(),
            arguments=parse_tool_arguments(legacy.get("arguments")),
            signature=thought_signature_from_obj(legacy),
        ))
    # Anthropic-style / Gemini parts mixed into content.
    content = message.get("content")
    if isinstance(content, list):
        for i, part in enumerate(content):
            if not isinstance(part, dict):
                continue
            ptype = str(part.get("type") or "")
            if ptype in ("tool_use", "function_call", "tool_call"):
                name = str(part.get("name") or "").strip()
                if not name:
                    continue
                args = parse_tool_arguments(
                    part.get("input", part.get("arguments", part.get("args"))))
                out.append(_extracted_tool_call(
                    cid=str(part.get("id") or f"part_{i}"),
                    name=name,
                    arguments=args,
                    signature=thought_signature_from_obj(part),
                ))
    if out and not str(out[0].get("thought_signature") or "").strip():
        fallback = thought_signature_from_obj(message)
        if not fallback and isinstance(content, list):
            for part in content:
                fallback = thought_signature_from_obj(part)
                if fallback:
                    break
        if fallback:
            out[0]["thought_signature"] = fallback
    return out


_BTFTOOL_FENCE_RE = re.compile(
    r"```(?:btftool|tool_call|tool-call)\s*\n(.*?)```",
    re.DOTALL | re.IGNORECASE,
)
_XML_TOOL_RE = re.compile(
    r"<tool_call>\s*(.*?)\s*</tool_call>",
    re.DOTALL | re.IGNORECASE,
)


def _tool_call_from_obj(obj: Any, idx: int) -> Optional[Dict[str, Any]]:
    if not isinstance(obj, dict):
        return None
    name = str(obj.get("name") or obj.get("tool") or "").strip()
    fn = obj.get("function") if isinstance(obj.get("function"), dict) else {}
    if fn:
        name = name or str(fn.get("name") or "").strip()
        args = parse_tool_arguments(fn.get("arguments", obj.get("arguments")))
    else:
        args = obj.get("arguments") or obj.get("parameters") or obj.get("args")
        if not isinstance(args, dict):
            args = parse_tool_arguments(args)
        if not args:
            args = {
                k: v for k, v in obj.items()
                if k not in ("name", "tool", "function", "id", "type")
            }
    if name not in AI_VIEWER_TOOL_NAMES:
        return None
    ok, err = validate_tool_call(name, args)
    if err:
        return None
    return {"id": f"text_{idx}", "name": name, "arguments": ok or args}


def parse_tool_calls_from_text(text: str) -> List[Dict[str, Any]]:
    """Parse ```btftool fences and <tool_call> blobs (models without native tools)."""
    out: List[Dict[str, Any]] = []
    seen = set()

    def _add(obj: Any) -> None:
        call = _tool_call_from_obj(obj, len(out))
        if not call:
            return
        key = (call["name"], json.dumps(call["arguments"], sort_keys=True, default=str))
        if key in seen:
            return
        seen.add(key)
        out.append(call)

    src = text or ""
    for m in _BTFTOOL_FENCE_RE.finditer(src):
        body = (m.group(1) or "").strip()
        try:
            data = json.loads(body)
        except (TypeError, ValueError):
            continue
        if isinstance(data, list):
            for item in data:
                _add(item)
        else:
            _add(data)
    for m in _XML_TOOL_RE.finditer(src):
        body = (m.group(1) or "").strip()
        try:
            _add(json.loads(body))
            continue
        except (TypeError, ValueError):
            pass
        lines = body.split("\n", 1)
        if len(lines) == 2:
            try:
                _add({"name": lines[0].strip(), "arguments": json.loads(lines[1])})
            except (TypeError, ValueError):
                pass
    return out


def merge_tool_calls(
    structured: Sequence[Dict[str, Any]],
    from_text: Sequence[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """Prefer native tool_calls; append unique text-parsed calls."""
    out: List[Dict[str, Any]] = []
    seen = set()
    for call in list(structured or []) + list(from_text or []):
        if not isinstance(call, dict) or not call.get("name"):
            continue
        key = (
            str(call.get("name")),
            json.dumps(call.get("arguments") or {}, sort_keys=True, default=str),
        )
        if key in seen:
            continue
        seen.add(key)
        out.append(dict(call))
    return out


def strip_parsed_tool_markup(text: str) -> str:
    """Remove btftool fences / XML after they were turned into GUI cards."""
    out = _BTFTOOL_FENCE_RE.sub("", text or "")
    out = _XML_TOOL_RE.sub("", out)
    return re.sub(r"\n{3,}", "\n\n", out).strip()


def _as_float_list(value: Any) -> List[float]:
    if not isinstance(value, (list, tuple)):
        return []
    out: List[float] = []
    for item in value:
        try:
            out.append(float(item))
        except (TypeError, ValueError):
            continue
    return out


def _fmt_trace_num(value: Any) -> str:
    try:
        n = float(value)
    except (TypeError, ValueError):
        return str(value)
    if n.is_integer():
        return str(int(n))
    return f"{n:g}"


def normalize_raw_metric(name: Any) -> str:
    """Map a metric alias onto one of ``AI_RAW_METRIC_NAMES`` (empty if unknown)."""
    want = str(name or "").strip().lower().replace("-", "_").replace(" ", "_")
    return _RAW_METRIC_ALIASES.get(want, "")


def is_query_tool(name: str) -> bool:
    return str(name or "") == AI_TOOL_QUERY_RAW_METRIC


def is_export_tool(name: str) -> bool:
    return str(name or "") == AI_TOOL_EXPORT_REPORT


def tool_mutates_gui(name: str) -> bool:
    """True when applying the tool changes timeline / inspector state."""
    return str(name or "") in (
        AI_TOOL_SET_CURSORS,
        AI_TOOL_ZOOM_TO_RANGE,
        AI_TOOL_HIGHLIGHT_TASK,
        AI_TOOL_SET_VIEW_MODE,
        AI_TOOL_OPEN_CORRIDOR,
        AI_TOOL_ADD_ANNOTATION,
    )


def tool_batch_auto_runs(tools: Optional[Sequence[Any]]) -> bool:
    """Query-only batches run immediately (no Apply card)."""
    names = [str((t or {}).get("name") or "") for t in (tools or [])]
    return bool(names) and all(is_query_tool(n) for n in names)


def validate_tool_call(name: str, args: Optional[Dict[str, Any]]) -> Tuple[Optional[Dict[str, Any]], str]:
    """Return ``(normalised_args, error)``. error is empty on success."""
    a = dict(args or {})
    if name == AI_TOOL_SET_CURSORS:
        times = _as_float_list(a.get("timestamps"))
        if not times:
            return None, "timestamps must be a non-empty number array"
        times = times[:_MAX_CURSORS_TOOL]
        return {"timestamps": times}, ""
    if name == AI_TOOL_ZOOM_TO_RANGE:
        try:
            lo = float(a.get("start_time"))
            hi = float(a.get("end_time"))
        except (TypeError, ValueError):
            return None, "start_time and end_time must be numbers"
        if hi == lo:
            return None, "start_time and end_time must differ"
        if hi < lo:
            lo, hi = hi, lo
        return {"start_time": lo, "end_time": hi}, ""
    if name == AI_TOOL_HIGHLIGHT_TASK:
        key = str(a.get("task_name_or_id") or "").strip()
        return {"task_name_or_id": key}, ""
    if name == AI_TOOL_SET_VIEW_MODE:
        mode = str(a.get("mode") or "").strip().lower()
        if mode not in ("task", "core"):
            return None, 'mode must be "task" or "core"'
        ori_raw = a.get("orientation")
        ori = None
        if ori_raw not in (None, ""):
            ori = str(ori_raw).strip().lower()
            if ori in ("h", "horiz"):
                ori = "horizontal"
            if ori in ("v", "vert"):
                ori = "vertical"
            if ori not in ("horizontal", "vertical"):
                return None, 'orientation must be "horizontal" or "vertical"'
        out: Dict[str, Any] = {"mode": mode}
        if ori:
            out["orientation"] = ori
        return out, ""
    if name == AI_TOOL_OPEN_CORRIDOR:
        src = str(a.get("core_from") or "").strip()
        dst = str(a.get("core_to") or "").strip()
        return {"core_from": src, "core_to": dst}, ""
    if name == AI_TOOL_ADD_ANNOTATION:
        try:
            t = float(a.get("time"))
        except (TypeError, ValueError):
            return None, "time must be a number"
        note = str(a.get("note") or "").strip()
        if not note:
            return None, "note must be a non-empty string"
        if len(note) > _MAX_ANNOTATION_NOTE:
            note = note[:_MAX_ANNOTATION_NOTE].rstrip()
        return {"time": t, "note": note}, ""
    if name == AI_TOOL_QUERY_RAW_METRIC:
        task = str(a.get("task") or "").strip()
        if not task:
            return None, "task must be a non-empty string"
        metric = normalize_raw_metric(a.get("metric"))
        if not metric:
            return None, (
                "metric must be one of: " + ", ".join(AI_RAW_METRIC_NAMES)
            )
        return {"task": task, "metric": metric}, ""
    if name == AI_TOOL_EXPORT_REPORT:
        fmt = str(a.get("format") or "html").strip().lower()
        if fmt in ("htm", "html"):
            fmt = "html"
        elif fmt == "csv":
            fmt = "csv"
        else:
            return None, 'format must be "html" or "csv"'
        return {"format": fmt}, ""
    return None, f"unknown tool {name!r}"


def summarise_tool_call(name: str, args: Optional[Dict[str, Any]]) -> str:
    """One-line label for a tool card (e.g. Set cursors at 3099000, 3133000)."""
    a = dict(args or {})
    if name == AI_TOOL_SET_CURSORS:
        times = _as_float_list(a.get("timestamps"))
        if not times:
            return "Set cursors"
        shown = ", ".join(_fmt_trace_num(t) for t in times[:_MAX_CURSORS_TOOL])
        return f"Set cursors at [{shown}]"
    if name == AI_TOOL_ZOOM_TO_RANGE:
        try:
            lo, hi = float(a["start_time"]), float(a["end_time"])
            return f"Zoom to range {_fmt_trace_num(lo)}–{_fmt_trace_num(hi)}"
        except (KeyError, TypeError, ValueError):
            return "Zoom to range"
    if name == AI_TOOL_HIGHLIGHT_TASK:
        key = str(a.get("task_name_or_id") or "").strip()
        return "Clear task highlight" if not key else f"Highlight task {key}"
    if name == AI_TOOL_SET_VIEW_MODE:
        mode = str(a.get("mode") or "?").strip()
        ori = str(a.get("orientation") or "").strip()
        label = f"Set view mode {mode}"
        if ori:
            label += f", {ori}"
        return label
    if name == AI_TOOL_OPEN_CORRIDOR:
        src = str(a.get("core_from") or "").strip()
        dst = str(a.get("core_to") or "").strip()
        if src and dst:
            return f"Open corridor inspector {src} → {dst}"
        return "Open corridor inspector"
    if name == AI_TOOL_ADD_ANNOTATION:
        note = str(a.get("note") or "").strip() or "annotation"
        try:
            t = float(a.get("time"))
            return f"Add annotation at {_fmt_trace_num(t)}: {note}"
        except (TypeError, ValueError):
            return f"Add annotation: {note}"
    if name == AI_TOOL_QUERY_RAW_METRIC:
        task = str(a.get("task") or "").strip() or "?"
        metric = normalize_raw_metric(a.get("metric")) or str(a.get("metric") or "?")
        return f"Query {metric} for {task}"
    if name == AI_TOOL_EXPORT_REPORT:
        fmt = str(a.get("format") or "html").strip().lower() or "html"
        return f"Export {fmt} report"
    return name.replace("_", " ")


def tool_result_payload(ok: bool, message: str, **extra: Any) -> Dict[str, Any]:
    data = {"ok": bool(ok), "message": str(message)}
    data.update(extra)
    return data


def format_tool_result_content(result: Dict[str, Any]) -> str:
    """JSON string sent back to the model as ``role: tool`` content."""
    return json.dumps(result, default=str)


def canonical_assistant_tool_message(
    content: Any,
    tool_calls: Sequence[Dict[str, Any]],
) -> Dict[str, Any]:
    """OpenAI-shaped assistant turn with ``tool_calls`` (Gemini-safe)."""
    calls_out: List[Dict[str, Any]] = []
    for i, call in enumerate(tool_calls or []):
        if not isinstance(call, dict):
            continue
        name = str(call.get("name") or "").strip()
        if not name:
            continue
        cid = str(call.get("id") or f"call_{i}").strip() or f"call_{i}"
        args = call.get("arguments")
        if isinstance(args, str):
            arg_s = args
        else:
            arg_s = json.dumps(
                args if isinstance(args, dict) else {}, default=str)
        entry: Dict[str, Any] = {
            "id": cid,
            "type": "function",
            "function": {"name": name, "arguments": arg_s},
        }
        sig = str(call.get("thought_signature") or "").strip() or (
            thought_signature_from_obj(call)
        )
        if sig:
            attach_thought_signature(entry, sig)
        calls_out.append(entry)
    text = message_content_text(content) if content is not None else ""
    msg: Dict[str, Any] = {"role": "assistant", "content": text or None}
    if calls_out:
        msg["tool_calls"] = calls_out
    return msg


def tool_result_message(
    *,
    tool_call_id: str,
    name: str,
    content: Any,
) -> Dict[str, Any]:
    """``role=tool`` follow-up. Gemini requires a non-empty function name."""
    cid = str(tool_call_id or "").strip() or "call_0"
    fname = str(name or "").strip()
    if isinstance(content, str):
        body = content
    elif isinstance(content, dict):
        body = format_tool_result_content(content)
    else:
        body = format_tool_result_content(
            {"ok": False, "message": str(content or "")})
    out: Dict[str, Any] = {
        "role": "tool",
        "tool_call_id": cid,
        "content": body,
    }
    if fname:
        out["name"] = fname
    return out


def normalize_tool_chat_messages(
    messages: Sequence[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """Fill ``name`` on tool follow-ups (Gemini OpenAI-compat).

    Gemini maps ``role=tool`` to ``function_response`` and rejects an empty
    name. Match by ``tool_call_id``, then by order after the last assistant
    tool_calls.
    """
    out: List[Dict[str, Any]] = []
    unused: List[Tuple[str, str]] = []
    for msg in messages or []:
        if not isinstance(msg, dict):
            continue
        role = str(msg.get("role") or "")
        if role == "assistant":
            extracted = extract_tool_calls(msg)
            if extracted:
                canon = canonical_assistant_tool_message(
                    msg.get("content"), extracted)
                out.append(canon)
                unused = [
                    (str(c.get("id") or ""), str(c.get("name") or "").strip())
                    for c in extract_tool_calls(canon)
                    if str(c.get("id") or "") and str(c.get("name") or "").strip()
                ]
            else:
                out.append(dict(msg))
                unused = []
            continue
        if role == "tool":
            copied = dict(msg)
            cid = str(copied.get("tool_call_id") or copied.get("id") or "").strip()
            name = str(copied.get("name") or "").strip()
            if not name and cid:
                for i, (uid, uname) in enumerate(unused):
                    if uid == cid:
                        name = uname
                        unused.pop(i)
                        break
            if not name and unused:
                uid, uname = unused.pop(0)
                name = uname
                if not cid:
                    cid = uid
            elif name and cid:
                unused = [(i, n) for i, n in unused if i != cid]
            if cid:
                copied["tool_call_id"] = cid
            if name:
                copied["name"] = name
            out.append(copied)
            continue
        out.append(dict(msg))
    return out


def parse_ai_auto_apply(value: Any) -> bool:
    """Settings → AI auto-apply flag (default False = require confirm)."""
    if value is True:
        return True
    if value is False or value is None:
        return False
    return str(value).strip().lower() in ("1", "true", "yes", "on")


def max_tool_rounds() -> int:
    return _MAX_TOOL_ROUNDS


_TASK_ID_RE = re.compile(r"\[(\d+)\]\s*$")
_TASK_EMBEDDED_RE = re.compile(r"([A-Za-z_][\w]*\[\d+\])")
_CORE_SUFFIX_RE = re.compile(r"\s*\((?:core\s*)?\d+\)\s*$", re.IGNORECASE)
_CORE_NUM_RE = re.compile(r"^(?:core[\s_-]*)?(\d+)$", re.IGNORECASE)
_CORE_SHORT_RE = re.compile(r"^c(\d+)$", re.IGNORECASE)


def normalize_task_lookup_query(task_name_or_id: str) -> str:
    """Strip mermaid decorations such as ``Low[266] (Core 0)`` → ``Low[266]``."""
    text = (task_name_or_id or "").strip()
    if not text:
        return ""
    stripped = _CORE_SUFFIX_RE.sub("", text).strip() or text
    m = _TASK_EMBEDDED_RE.search(stripped)
    return m.group(1) if m else stripped


def task_lookup_keys(task_name_or_id: str) -> List[str]:
    """Candidate keys for resolving a highlight target (name, id, merge key)."""
    raw = (task_name_or_id or "").strip()
    if not raw:
        return []
    keys: List[str] = []
    for alias in _task_match_aliases(raw):
        if alias not in keys:
            keys.append(alias)
        low = alias.lower()
        if low not in keys:
            keys.append(low)
    return keys


def _task_match_aliases(raw: str) -> List[str]:
    """Display name / id / merge-key spellings that should match *raw*."""
    text = (raw or "").strip()
    if not text:
        return []
    aliases = [text]
    if text.startswith("\x00"):
        sep = text.find("\x00", 1)
        if sep > 0:
            tid, name = text[1:sep], text[sep + 1:]
            if name and name != "TICK":
                aliases.extend((f"{name}[{tid}]", name, tid))
            elif name:
                aliases.append(name)
        return [a for a in aliases if a]
    m = _TASK_ID_RE.search(text)
    if m:
        aliases.append(m.group(1))
        prefix = text[: m.start()].strip()
        if prefix:
            aliases.append(prefix)
    if text.isdigit():
        aliases.append(f"[{text}]")
    return [a for a in aliases if a]


def resolve_task_key(
    task_name_or_id: str,
    candidates: Sequence[str],
) -> Optional[str]:
    """Pick the best matching task/merge key from *candidates*."""
    raw = (task_name_or_id or "").strip()
    if not raw:
        return None
    names = [str(c) for c in candidates if c]
    if not names:
        return None
    queries = [raw]
    norm = normalize_task_lookup_query(raw)
    if norm and norm not in queries:
        queries.append(norm)

    exact = {n: n for n in names}
    lower = {n.lower(): n for n in names}
    by_alias: Dict[str, List[str]] = {}
    for name in names:
        for alias in _task_match_aliases(name):
            bucket = by_alias.setdefault(alias.lower(), [])
            if name not in bucket:
                bucket.append(name)

    for want in queries:
        if want in exact:
            return exact[want]
        if want.lower() in lower:
            return lower[want.lower()]
        hits = by_alias.get(want.lower()) or []
        if len(hits) == 1:
            return hits[0]
        if hits and want.isdigit():
            return hits[0]
        want_l = want.lower()
        prefix: List[str] = []
        contains: List[str] = []
        for alias, origs in by_alias.items():
            if alias.startswith(want_l):
                prefix.extend(origs)
            if want_l in alias:
                contains.extend(origs)
        prefix_u = list(dict.fromkeys(prefix))
        if len(prefix_u) == 1:
            return prefix_u[0]
        contains_u = list(dict.fromkeys(contains))
        if len(contains_u) == 1:
            return contains_u[0]
    return None


def _core_match_aliases(raw: str) -> List[str]:
    """Core_0 / Core 0 / 0 / c0 spellings that should match *raw*."""
    text = (raw or "").strip()
    if not text:
        return []
    aliases = [text]
    compact = re.sub(r"[\s_-]+", "_", text)
    if compact not in aliases:
        aliases.append(compact)
    spaced = text.replace("_", " ")
    if spaced not in aliases:
        aliases.append(spaced)
    m = _CORE_NUM_RE.match(text) or _CORE_SHORT_RE.match(text)
    if m:
        n = str(int(m.group(1)))
        aliases.extend((n, f"Core_{n}", f"core_{n}", f"Core {n}", f"c{n}", f"C{n}"))
    return [a for a in dict.fromkeys(aliases) if a]


def resolve_core_key(
    core_name_or_id: str,
    candidates: Sequence[str],
) -> Optional[str]:
    """Pick the best matching core name from *candidates* (e.g. Core_0)."""
    want = (core_name_or_id or "").strip()
    if not want:
        return None
    names = [str(c) for c in candidates if c]
    if not names:
        return None
    if want in names:
        return want
    lower = {n.lower(): n for n in names}
    if want.lower() in lower:
        return lower[want.lower()]
    by_alias: Dict[str, List[str]] = {}
    for name in names:
        for alias in _core_match_aliases(name):
            bucket = by_alias.setdefault(alias.lower(), [])
            if name not in bucket:
                bucket.append(name)
    hits: List[str] = []
    for alias in _core_match_aliases(want):
        for orig in by_alias.get(alias.lower(), []):
            if orig not in hits:
                hits.append(orig)
    if hits:
        return hits[0]
    return None


def _csv_escape_rows(rows: Sequence[Sequence[Any]]) -> str:
    buf = io.StringIO()
    writer = csv.writer(buf, lineterminator="\n")
    for row in rows:
        writer.writerow(["" if c is None else str(c) for c in row])
    return buf.getvalue()


def build_ai_report_csv(
    *,
    meta: Optional[Dict[str, Any]] = None,
    gui: Optional[Dict[str, Any]] = None,
    findings: str = "",
    annotations: Optional[Sequence[Dict[str, Any]]] = None,
    conversation: str = "",
) -> str:
    """Tabular AI report (findings + GUI state + conversation)."""
    rows: List[List[str]] = [["section", "key", "value"]]
    for key, val in dict(meta or {}).items():
        rows.append(["meta", str(key), str(val)])
    gui_d = dict(gui or {})
    cursors = gui_d.pop("cursors", None)
    if cursors is not None:
        if isinstance(cursors, (list, tuple)):
            rows.append(["gui", "cursors", ";".join(f"{c:g}" if isinstance(c, (int, float)) else str(c) for c in cursors)])
        else:
            rows.append(["gui", "cursors", str(cursors)])
    for key, val in gui_d.items():
        if key == "annotations":
            continue
        rows.append(["gui", str(key), str(val)])
    ann_list = list(annotations or [])
    if not ann_list and isinstance(gui, dict):
        extra = gui.get("annotations")
        if isinstance(extra, (list, tuple)):
            ann_list = list(extra)
    for ann in ann_list:
        if not isinstance(ann, dict):
            continue
        rows.append(["annotation", str(ann.get("time", "")), str(ann.get("note", ""))])
    for i, line in enumerate((findings or "").splitlines()):
        if line.strip():
            rows.append(["finding", str(i + 1), line])
    for i, line in enumerate((conversation or "").splitlines()):
        rows.append(["conversation", str(i + 1), line])
    return _csv_escape_rows(rows)


def _html_escape(text: Any) -> str:
    return (
        str(text or "")
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def build_ai_report_html(
    *,
    meta: Optional[Dict[str, Any]] = None,
    gui: Optional[Dict[str, Any]] = None,
    findings: str = "",
    annotations: Optional[Sequence[Dict[str, Any]]] = None,
    conversation_html: str = "",
) -> str:
    """Standalone HTML report wrapping findings, GUI state, and the chat."""
    meta_rows = "".join(
        f"<tr><th>{_html_escape(k)}</th><td>{_html_escape(v)}</td></tr>"
        for k, v in dict(meta or {}).items()
    )
    gui_d = dict(gui or {})
    gui_rows = []
    for key, val in gui_d.items():
        if key == "annotations":
            continue
        if key == "cursors" and isinstance(val, (list, tuple)):
            val = ", ".join(f"{c:g}" if isinstance(c, (int, float)) else str(c) for c in val)
        gui_rows.append(f"<tr><th>{_html_escape(key)}</th><td>{_html_escape(val)}</td></tr>")
    anns = list(annotations or [])
    if not anns and isinstance(gui_d.get("annotations"), list):
        anns = list(gui_d["annotations"])
    ann_rows = "".join(
        f"<tr><td>{_html_escape(a.get('time', ''))}</td>"
        f"<td>{_html_escape(a.get('note', ''))}</td></tr>"
        for a in anns if isinstance(a, dict)
    ) or "<tr><td colspan=\"2\">None</td></tr>"
    findings_body = (
        f"<pre>{_html_escape(findings)}</pre>" if (findings or "").strip()
        else "<p>No findings for the current scope.</p>"
    )
    conv = conversation_html or ""
    return (
        "<!DOCTYPE html>\n<html lang=\"en\">\n<head>\n"
        "<meta charset=\"utf-8\">\n"
        "<title>BTF Viewer — AI Report</title>\n"
        "<style>\n"
        "body{background:#12161d;color:#dbe2ea;font-family:system-ui,-apple-system,"
        "'Segoe UI',sans-serif;font-size:13px;line-height:1.5;margin:0;padding:20px;}\n"
        "h1{font-size:18px;margin:0 0 4px;} h2{font-size:15px;margin:20px 0 8px;}\n"
        ".saved{color:#8b98a8;font-size:12px;margin:0 0 16px;}\n"
        "table{border-collapse:collapse;width:100%;margin:0 0 12px;}\n"
        "th,td{text-align:left;padding:4px 8px;border-bottom:1px solid #2b3442;"
        "vertical-align:top;}\n"
        "th{color:#8b98a8;font-weight:600;width:22%;}\n"
        "pre{background:#1a2230;border:1px solid #3a4658;border-radius:4px;"
        "padding:8px;overflow:auto;white-space:pre-wrap;}\n"
        "a{color:#5b9bd5;}\n"
        "</style>\n</head>\n<body>\n"
        "<h1>BTF Viewer — AI Report</h1>\n"
        f"<table>{meta_rows}</table>\n"
        "<h2>GUI state</h2>\n"
        f"<table>{''.join(gui_rows)}</table>\n"
        "<h2>Annotations</h2>\n"
        f"<table><tr><th>Time</th><th>Note</th></tr>{ann_rows}</table>\n"
        "<h2>Analysis Findings</h2>\n"
        f"{findings_body}\n"
        "<h2>Conversation</h2>\n"
        f"{conv}\n"
        "</body>\n</html>\n"
    )


def _in_time_range(t: Any, lo: Optional[float], hi: Optional[float]) -> bool:
    if lo is None or hi is None:
        return True
    try:
        v = float(t)
    except (TypeError, ValueError):
        return False
    return lo <= v <= hi


def _overlaps_range(start: Any, stop: Any, lo: Optional[float], hi: Optional[float]) -> bool:
    if lo is None or hi is None:
        return True
    try:
        a, b = float(start), float(stop)
    except (TypeError, ValueError):
        return False
    return b > lo and a < hi


def _task_candidates_from_trace(trace: Any) -> List[str]:
    names: List[str] = []
    for t in list(getattr(trace, "tasks", None) or []):
        names.append(str(t))
    smap = getattr(trace, "seg_map_by_merge_key", None)
    if isinstance(smap, dict):
        names.extend(str(k) for k in smap.keys())
    web_map = getattr(trace, "segByMergeKey", None)
    if web_map is not None and hasattr(web_map, "keys"):
        try:
            names.extend(str(k) for k in web_map.keys())
        except Exception:
            pass
    repr_map = getattr(trace, "task_repr", None) or getattr(trace, "taskRepr", None)
    if isinstance(repr_map, dict):
        names.extend(str(v) for v in repr_map.values() if v)
        names.extend(str(k) for k in repr_map.keys())
    return names


def _segs_for_mk(trace: Any, mk: str) -> List[Any]:
    smap = getattr(trace, "seg_map_by_merge_key", None)
    if isinstance(smap, dict) and mk in smap:
        return list(smap.get(mk) or [])
    web_map = getattr(trace, "segByMergeKey", None)
    if web_map is None:
        return []
    getter = getattr(web_map, "get", None)
    if callable(getter):
        return list(getter(mk) or [])
    try:
        return list(web_map[mk])  # type: ignore[index]
    except Exception:
        return []


def _medium_labels(ep: Any) -> List[str]:
    out: List[str] = []
    for item in getattr(ep, "medium_tasks", None) or getattr(ep, "mediumTasks", None) or []:
        if isinstance(item, str):
            if item:
                out.append(item)
        elif isinstance(item, dict):
            label = str(item.get("label") or item.get("mk") or "")
            if label:
                out.append(label)
        else:
            label = str(getattr(item, "label", "") or "")
            if label:
                out.append(label)
    return out


def query_raw_metric(
    trace: Any,
    task: str,
    metric: str,
    *,
    lo: Optional[float] = None,
    hi: Optional[float] = None,
    findings_text: str = "",
) -> Dict[str, Any]:
    """Return a tool-result payload with per-task samples for *metric*."""
    if trace is None:
        return tool_result_payload(False, "No trace loaded")
    metric_id = normalize_raw_metric(metric)
    if not metric_id:
        return tool_result_payload(
            False, "metric must be one of: " + ", ".join(AI_RAW_METRIC_NAMES))
    resolved = resolve_task_key(str(task or "").strip(), _task_candidates_from_trace(trace))
    if not resolved:
        return tool_result_payload(False, f"Unknown task {task!r}")
    try:
        from .parser import _task_merge_key
        mk = _task_merge_key(resolved)
    except Exception:
        mk = resolved
    repr_map = getattr(trace, "task_repr", None) or getattr(trace, "taskRepr", None) or {}
    label = ""
    if isinstance(repr_map, dict):
        label = str(repr_map.get(mk) or repr_map.get(resolved) or "")
    if not label:
        label = str(resolved)
    scope = {"lo": lo, "hi": hi} if lo is not None and hi is not None else None
    data: Dict[str, Any] = {
        "task": label,
        "task_key": mk,
        "metric": metric_id,
        "scope": scope,
    }
    if metric_id == AI_RAW_METRIC_FINDINGS:
        aliases = [a for a in task_lookup_keys(task) + task_lookup_keys(label) + [label, str(resolved)] if a]
        hits = []
        for line in (findings_text or "").splitlines():
            low = line.lower()
            if any(a.lower() in low for a in aliases):
                hits.append(line)
        truncated = len(hits) > _MAX_RAW_METRIC_ROWS
        data["rows"] = hits[:_MAX_RAW_METRIC_ROWS]
        data["count"] = len(hits)
        data["truncated"] = truncated
        msg = f"{len(hits)} finding line(s) mentioning {label}"
        return tool_result_payload(True, msg, data=data)

    if metric_id == AI_RAW_METRIC_PRIORITY:
        by_mk = getattr(trace, "priority_episodes_by_mk", None) or getattr(
            trace, "priorityEpisodesByMk", None)
        eps: List[Any] = []
        if isinstance(by_mk, dict):
            eps = list(by_mk.get(mk) or [])
        elif by_mk is not None and hasattr(by_mk, "get"):
            eps = list(by_mk.get(mk) or [])
        if not eps:
            all_eps = getattr(trace, "priority_episodes", None) or getattr(
                trace, "priorityEpisodes", None) or []
            for ep in all_eps:
                ep_mk = getattr(ep, "mk", None) or (ep.get("mk") if isinstance(ep, dict) else "")
                if ep_mk == mk:
                    eps.append(ep)
        rows = []
        for ep in eps:
            start = getattr(ep, "start_ns", None)
            stop = getattr(ep, "stop_ns", None)
            if start is None and isinstance(ep, dict):
                start, stop = ep.get("startNs"), ep.get("stopNs")
            if not _overlaps_range(start, stop, lo, hi):
                continue
            inherited = bool(getattr(ep, "inherited", None) if not isinstance(ep, dict)
                             else ep.get("inherited"))
            suspect = bool(getattr(ep, "inversion_suspect", None) if not isinstance(ep, dict)
                           else ep.get("inversionSuspect"))
            pattern = getattr(ep, "pattern", None) if not isinstance(ep, dict) else ep.get("pattern")
            base = getattr(ep, "base_pri", None) if not isinstance(ep, dict) else ep.get("basePri")
            peak = getattr(ep, "peak_pri", None) if not isinstance(ep, dict) else ep.get("peakPri")
            rows.append({
                "start": start,
                "stop": stop,
                "duration": (None if start is None or stop is None else int(stop) - int(start)),
                "base_pri": base,
                "peak_pri": peak,
                "inherited": inherited,
                "inversion_suspect": suspect,
                "medium_tasks": _medium_labels(ep),
                "pattern": pattern or "",
            })
        truncated = len(rows) > _MAX_RAW_METRIC_ROWS
        data["episodes"] = rows[:_MAX_RAW_METRIC_ROWS]
        data["count"] = len(rows)
        data["truncated"] = truncated
        msg = f"{len(rows)} priority inheritance episode(s) for {label}"
        return tool_result_payload(True, msg, data=data)

    if metric_id == AI_RAW_METRIC_EXECUTION:
        segs = _segs_for_mk(trace, mk)
        samples = []
        total = 0
        max_dur = 0
        max_at = None
        for seg in segs:
            start = getattr(seg, "start", None) if not isinstance(seg, dict) else seg.get("start")
            end = getattr(seg, "end", None) if not isinstance(seg, dict) else seg.get("end")
            core = getattr(seg, "core", None) if not isinstance(seg, dict) else seg.get("core")
            if not _overlaps_range(start, end, lo, hi):
                continue
            dur = int(end) - int(start) if start is not None and end is not None else 0
            if lo is not None and hi is not None and start is not None and end is not None:
                clip_lo = max(int(start), int(lo))
                clip_hi = min(int(end), int(hi))
                dur = max(0, clip_hi - clip_lo)
            total += dur
            if dur >= max_dur:
                max_dur = dur
                max_at = start
            samples.append({
                "start": start, "stop": end, "duration": dur, "core": core or "",
            })
        truncated = len(samples) > _MAX_RAW_METRIC_ROWS
        data.update({
            "count": len(samples),
            "total": total,
            "max": max_dur,
            "max_at": max_at,
            "mean": (total / len(samples)) if samples else 0,
            "slices": samples[:_MAX_RAW_METRIC_ROWS],
            "truncated": truncated,
        })
        msg = f"{len(samples)} execution slice(s) for {label}"
        return tool_result_payload(True, msg, data=data)

    if metric_id == AI_RAW_METRIC_MIGRATIONS:
        by_mk = getattr(trace, "migrations_by_mk", None) or getattr(
            trace, "migrationsByMk", None)
        migs: List[Any] = []
        if isinstance(by_mk, dict):
            migs = list(by_mk.get(mk) or [])
        elif by_mk is not None and hasattr(by_mk, "get"):
            migs = list(by_mk.get(mk) or [])
        if not migs:
            for m in getattr(trace, "migrations", None) or []:
                m_mk = getattr(m, "merge_key", None) or getattr(m, "mergeKey", None)
                if isinstance(m, dict):
                    m_mk = m.get("merge_key") or m.get("mergeKey")
                if m_mk == mk:
                    migs.append(m)
        rows = []
        for m in migs:
            ns = getattr(m, "ns", None) if not isinstance(m, dict) else m.get("ns")
            if not _in_time_range(ns, lo, hi):
                continue
            src = getattr(m, "from_core", None) if not isinstance(m, dict) else (
                m.get("from_core") or m.get("fromCore"))
            dst = getattr(m, "to_core", None) if not isinstance(m, dict) else (
                m.get("to_core") or m.get("toCore"))
            rows.append({"time": ns, "from": src or "", "to": dst or ""})
        truncated = len(rows) > _MAX_RAW_METRIC_ROWS
        data["events"] = rows[:_MAX_RAW_METRIC_ROWS]
        data["count"] = len(rows)
        data["truncated"] = truncated
        msg = f"{len(rows)} migration(s) for {label}"
        return tool_result_payload(True, msg, data=data)

    if metric_id == AI_RAW_METRIC_BLOCKING:
        segs = sorted(
            _segs_for_mk(trace, mk),
            key=lambda s: getattr(s, "start", None) if not isinstance(s, dict) else s.get("start"),
        )
        gaps = []
        for prev, nxt in zip(segs, segs[1:]):
            prev_end = getattr(prev, "end", None) if not isinstance(prev, dict) else prev.get("end")
            nxt_start = getattr(nxt, "start", None) if not isinstance(nxt, dict) else nxt.get("start")
            if prev_end is None or nxt_start is None:
                continue
            gap = int(nxt_start) - int(prev_end)
            if gap <= 0:
                continue
            if not _in_time_range(nxt_start, lo, hi):
                continue
            gaps.append({"time": nxt_start, "gap": gap})
        truncated = len(gaps) > _MAX_RAW_METRIC_ROWS
        max_gap = max((g["gap"] for g in gaps), default=0)
        total_gap = sum(g["gap"] for g in gaps)
        data.update({
            "count": len(gaps),
            "max": max_gap,
            "total": total_gap,
            "gaps": gaps[:_MAX_RAW_METRIC_ROWS],
            "truncated": truncated,
        })
        msg = f"{len(gaps)} blocking gap(s) for {label}"
        return tool_result_payload(True, msg, data=data)

    # sync STI events whose note mentions the task
    sti = getattr(trace, "sti_events", None) or getattr(trace, "stiEvents", None) or []
    aliases = [a.lower() for a in task_lookup_keys(task) + task_lookup_keys(label) if a]
    rows = []
    for ev in sti:
        t = getattr(ev, "time", None) if not isinstance(ev, dict) else ev.get("time")
        if not _in_time_range(t, lo, hi):
            continue
        note = str(getattr(ev, "note", None) if not isinstance(ev, dict) else ev.get("note") or "")
        target = str(getattr(ev, "target", None) if not isinstance(ev, dict) else ev.get("target") or "")
        event = str(getattr(ev, "event", None) if not isinstance(ev, dict) else ev.get("event") or "")
        blob = f"{note} {target} {event}".lower()
        if not any(a in blob for a in aliases):
            continue
        core = getattr(ev, "core", None) if not isinstance(ev, dict) else ev.get("core")
        rows.append({
            "time": t,
            "core": core or "",
            "target": target,
            "event": event,
            "note": note,
        })
    truncated = len(rows) > _MAX_RAW_METRIC_ROWS
    data["events"] = rows[:_MAX_RAW_METRIC_ROWS]
    data["count"] = len(rows)
    data["truncated"] = truncated
    msg = f"{len(rows)} sync STI event(s) for {label}"
    return tool_result_payload(True, msg, data=data)

