"""Viewer tool-calling schema for the AI Assistant (Desktop + Web).

OpenAI / Ollama / Gemini OpenAI-compat ``tools`` definitions. Keep in sync
with ``web/src/utils/aiTools.js``.
"""
from __future__ import annotations

import json
import re
import urllib.parse
from typing import Any, Dict, List, Optional, Sequence, Tuple

AI_TOOL_SET_CURSORS = "set_cursors"
AI_TOOL_ZOOM_TO_RANGE = "zoom_to_range"
AI_TOOL_HIGHLIGHT_TASK = "highlight_task"
AI_TOOL_SET_VIEW_MODE = "set_view_mode"
AI_TOOL_OPEN_CORRIDOR = "open_corridor_inspector"

AI_VIEWER_TOOL_NAMES: Tuple[str, ...] = (
    AI_TOOL_SET_CURSORS,
    AI_TOOL_ZOOM_TO_RANGE,
    AI_TOOL_HIGHLIGHT_TASK,
    AI_TOOL_SET_VIEW_MODE,
    AI_TOOL_OPEN_CORRIDOR,
)

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
    "When the user asks to show, focus, inspect, zoom, highlight, or jump to a "
    "time range, task, or core pair, you MUST invoke the matching viewer tool "
    "(native function call) in addition to your markdown answer. Valid tools: "
    "set_cursors, zoom_to_range, highlight_task, set_view_mode, "
    "open_corridor_inspector. Tool timestamps use the same numeric trace time "
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
            out.append({"id": cid, "name": name, "arguments": args})
    legacy = message.get("function_call")
    if isinstance(legacy, dict) and legacy.get("name"):
        out.append({
            "id": str(legacy.get("id") or "call_0"),
            "name": str(legacy["name"]).strip(),
            "arguments": parse_tool_arguments(legacy.get("arguments")),
        })
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
                out.append({
                    "id": str(part.get("id") or f"part_{i}"),
                    "name": name,
                    "arguments": args,
                })
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
    return None, f"unknown tool {name!r}"


def summarise_tool_call(name: str, args: Optional[Dict[str, Any]]) -> str:
    """One-line label for a tool card (e.g. Set cursors at 3099000, 3133000)."""
    a = dict(args or {})
    if name == AI_TOOL_SET_CURSORS:
        times = _as_float_list(a.get("timestamps"))
        if not times:
            return "Set cursors"
        shown = ", ".join(f"{t:g}" for t in times[:_MAX_CURSORS_TOOL])
        return f"Set cursors at [{shown}]"
    if name == AI_TOOL_ZOOM_TO_RANGE:
        try:
            lo, hi = float(a["start_time"]), float(a["end_time"])
            return f"Zoom to range {lo:g}–{hi:g}"
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
        calls_out.append({
            "id": cid,
            "type": "function",
            "function": {"name": name, "arguments": arg_s},
        })
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
