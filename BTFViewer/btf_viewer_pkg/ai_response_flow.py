"""One clean response block per user query (AI_RESPONSE_FLOW_TODO):

    user -> "Analysis completed · N.N s" -> collapsed "Tool usage · X calls /
    Y tools" -> final answer.

Pure helpers shared by the desktop log renderer and the exports.
Lockstep with ``web/src/utils/aiResponseFlow.js``.
"""
from __future__ import annotations

from typing import Any, Dict, List, Sequence, Set, Tuple

from .ai_tool_usage import record_tool_usage, summarize_tool_usage


def format_elapsed_seconds(s: Any) -> str:
    """``28.3`` — one decimal, matches the TODO's own examples."""
    try:
        n = max(0.0, float(s))
    except (TypeError, ValueError):
        n = 0.0
    return f"{round(n * 10) / 10:.1f}"


def format_analysis_status(elapsed_s: Any, labels: Dict[str, str] | None = None) -> str:
    """"Analysis completed · 28.3 s" / "分析完成 · 用時 28.3 秒"."""
    lab = labels or {}
    done = lab.get("analysis_completed") or "Analysis completed"
    time_word = f"{lab['time_used']} " if lab.get("time_used") else ""
    unit = lab.get("seconds_unit") or "s"
    out = f"{done} · {time_word}{format_elapsed_seconds(elapsed_s)} {unit}"
    return " ".join(out.split())


def tool_usage_from_chat_tools(tools: Sequence[Any]) -> Dict[str, Any]:
    """Roll up the chat-level tool list (name + status + result string) into the
    same shape as :func:`summarize_tool_usage`, so every count agrees."""
    u: Dict[str, Any] = {"calls": []}
    for t in tools or []:
        if not isinstance(t, dict) or not t.get("name"):
            continue
        failed = str(t.get("status") or "") == "failed"
        u = record_tool_usage(u, name=str(t.get("name")), result={
            "ok": not failed,
            "message": t.get("result"),
            "error": (t.get("result") or "failed") if failed else None,
        })
    return summarize_tool_usage(u)


def format_tool_usage_summary_line(
    tools: Sequence[Any],
    labels: Dict[str, str] | None = None,
) -> str:
    """"Tool usage · 5 calls / 5 tools" (+ " · 1 failed")."""
    lab = labels or {}
    s = tool_usage_from_chat_tools(tools)
    out = (
        f"{lab.get('tool_usage') or 'Tool usage'} · "
        f"{s['total']} {lab.get('calls') or 'calls'} / "
        f"{s['unique']} {lab.get('uniq_tools') or 'tools'}"
    )
    if s["failed"]:
        out += f" · {s['failed']} {lab.get('failed_word') or 'failed'}"
    return out


def _role(entry: Any) -> str:
    if isinstance(entry, dict):
        return str(entry.get("role") or "assistant")
    if isinstance(entry, (list, tuple)) and entry:
        return str(entry[0] or "assistant")
    return "assistant"


def _text(entry: Any) -> str:
    if isinstance(entry, dict):
        return str(entry.get("text") or entry.get("content") or "")
    if isinstance(entry, (list, tuple)) and len(entry) > 1:
        return str(entry[1] or "")
    return ""


def _tools(entry: Any) -> List[Dict[str, Any]]:
    if isinstance(entry, dict):
        raw = entry.get("tools")
        if isinstance(raw, list):
            return [t for t in raw if isinstance(t, dict)]
    return []


def plan_query_blocks(
    entries: Sequence[Any],
) -> Tuple[Set[int], Dict[int, Dict[str, Any]]]:
    """For a completed conversation, decide how each entry renders.

    Returns ``(hidden, meta)``:
    - ``hidden`` — interstitial narration turns and per-round tool cards for a
      query that has completed.
    - ``meta``   — ``{idx: {elapsed_s, tools, batch_ids}}`` for the entry that
      carries the status line + tool-usage summary (the final answer, or the
      last tool turn when there is no written answer).
    A query still running is left untouched. Lockstep with
    ``planQueryBlocks`` in aiResponseFlow.js.
    """
    hidden: Set[int] = set()
    meta: Dict[int, Dict[str, Any]] = {}
    n = len(entries)
    i = 0
    while i < n:
        if _role(entries[i]) != "user":
            i += 1
            continue
        user_idx = i
        j = i + 1
        rest: List[int] = []
        while j < n and _role(entries[j]) != "user":
            rest.append(j)
            j += 1
        tool_idxs = [k for k in rest if _role(entries[k]) == "assistant" and _tools(entries[k])]
        prose_idxs = [
            k for k in rest
            if _role(entries[k]) == "assistant" and _text(entries[k]).strip()
        ]
        all_tools: List[Dict[str, Any]] = []
        for k in tool_idxs:
            all_tools.extend(_tools(entries[k]))
        any_pending = any(
            str(t.get("status") or "pending") == "pending" for t in all_tools
        )
        user_entry = entries[user_idx] if isinstance(entries[user_idx], dict) else {}
        complete = bool(user_entry.get("turn_complete")) and not any_pending
        # Per-round tool cards are never shown in the chat — a tool-only turn
        # with no written prose is hidden even while the query is still running.
        # Only the one consolidated "Tool Usage" block surfaces tool activity.
        for k in tool_idxs:
            if not _text(entries[k]).strip():
                hidden.add(k)
        if complete and (tool_idxs or prose_idxs):
            answer_idx = prose_idxs[-1] if prose_idxs else None
            host = answer_idx if answer_idx is not None else (
                tool_idxs[-1] if tool_idxs else None)
            if host is not None:
                batch_ids: List[str] = []
                for k in tool_idxs:
                    bid = str((entries[k].get("batch_id") if isinstance(entries[k], dict) else "") or "")
                    if bid and bid not in batch_ids:
                        batch_ids.append(bid)
                meta[host] = {
                    "elapsed_s": float(user_entry.get("analysis_elapsed_s") or 0.0),
                    "tools": all_tools,
                    "batch_ids": batch_ids,
                }
                hidden.discard(host)
                # Hide only the assistant's own turns (interstitial narration +
                # per-round tool cards). Never hide the Evidence & Validation
                # panel (role 'evidence') or any other non-assistant entry.
                for k in rest:
                    if k != host and _role(entries[k]) == "assistant":
                        hidden.add(k)
        i = j
    return hidden, meta
