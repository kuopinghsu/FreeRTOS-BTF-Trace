"""Authoritative AI tool-usage record for one investigation.

One append-only list of per-call records lives on the Investigation Case
(``investigation_case["tool_usage"]``). Every displayed tool statistic — the
compact summary line, category counts, grouped ``xN`` rows, trace-query count,
the cost line's trace-query value, and the exported report — is derived from
:func:`summarize_tool_usage` so the numbers can never disagree.

Lockstep with ``web/src/utils/aiToolUsage.js``.
"""
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Sequence


AI_TOOL_USAGE_CATEGORIES = ("Evidence", "Analysis", "Verification", "Viewer")

# Tools that retrieve raw trace data. These count as "trace queries".
AI_TOOL_USAGE_EVIDENCE_TOOLS = (
    "query_raw_metric",
    "search_timeline",
    "detect_anomalies",
    "analyze_distribution",
    "analyze_periodicity",
    "find_related_findings",
    "explain_finding",
    "check_budget",
    "compare_tasks",
    "compare_performance",
)

# Tools that challenge or score a conclusion.
AI_TOOL_USAGE_VERIFICATION_TOOLS = (
    "verify_claim",
    "challenge_conclusion",
    "detect_contradictions",
    "assess_evidence_sufficiency",
    "score_investigation",
    "close_investigation",
)

# Tools that mutate the viewer or export.
AI_TOOL_USAGE_VIEWER_TOOLS = (
    "set_cursors",
    "zoom_to_range",
    "highlight_task",
    "set_view_mode",
    "open_corridor_inspector",
    "open_statistics_section",
    "add_annotation",
    "clear_marks",
    "reset_view",
    "bookmark_finding",
    "trigger_compare",
    "export_report",
    "export_investigation",
)

_EVIDENCE_SET = frozenset(AI_TOOL_USAGE_EVIDENCE_TOOLS)
_VERIFICATION_SET = frozenset(AI_TOOL_USAGE_VERIFICATION_TOOLS)
_VIEWER_SET = frozenset(AI_TOOL_USAGE_VIEWER_TOOLS)

_VERDICT_LABEL = {
    "confirmed": "Confirmed",
    "rejected": "Refuted",
    "refuted": "Refuted",
    "inconclusive": "Inconclusive",
}


def ai_tool_usage_category(name: str) -> str:
    """Map a tool name to one of AI_TOOL_USAGE_CATEGORIES. Default: Analysis."""
    n = str(name or "").strip()
    if n in _EVIDENCE_SET:
        return "Evidence"
    if n in _VERIFICATION_SET:
        return "Verification"
    if n in _VIEWER_SET:
        return "Viewer"
    return "Analysis"


def is_trace_query_tool(name: str) -> bool:
    """A trace query is any Evidence-category call."""
    return ai_tool_usage_category(name) == "Evidence"


def _result_ok(result: Any) -> bool:
    if not isinstance(result, dict):
        return True
    if result.get("ok") is False:
        return False
    err = result.get("error")
    if err not in (None, ""):
        return False
    st = str(result.get("status") or "").lower()
    if st in ("error", "failed", "failure"):
        return False
    return True


def _first_sentence(text: Any, max_len: int = 120) -> str:
    s = re.sub(r"\s+", " ", str(text or "")).strip()
    if not s:
        return ""
    cut = re.split(r"(?<=[.!?])\s", s, maxsplit=1)[0] or s
    if len(cut) > max_len:
        return cut[: max_len - 1].rstrip() + "…"
    return cut


def tool_brief_result(name: str, result: Any) -> str:
    """Short factual one-liner describing what a tool call contributed.

    Deterministic — derived from the structured result only, never synthesised.
    Returns '' when nothing concrete is available.
    """
    n = str(name or "").strip()
    if not isinstance(result, dict):
        return ""
    data = result.get("data") if isinstance(result.get("data"), dict) else result

    if n in ("verify_claim", "challenge_conclusion"):
        raw = str(
            data.get("verdict") or data.get("status") or result.get("message") or ""
        ).strip().lower()
        verdict = _VERDICT_LABEL.get(raw, raw[:1].upper() + raw[1:] if raw else "")
        reason = data.get("reason") or data.get("detail") or data.get("summary") or ""
        if not reason and isinstance(data.get("checks"), list):
            for c in data["checks"]:
                if isinstance(c, dict) and c.get("ok") is False:
                    reason = c.get("detail") or ""
                    break
        reason = str(reason).strip()
        if verdict and reason:
            return f"{verdict} — {_first_sentence(reason)}"
        if verdict:
            return verdict
        return ""

    if n == "query_raw_metric":
        metric = str(data.get("metric") or data.get("name") or "").strip()
        id_val = data.get("id")
        id_part = f"[{id_val}]" if id_val not in (None, "") else ""
        stat = str(data.get("stat") or data.get("aggregate") or "").strip()
        val = data.get("value") if data.get("value") is not None else data.get("result")
        unit = str(data.get("unit") or data.get("units") or "").strip()
        if unit and unit[:1].isalpha():
            unit = f" {unit}"
        if metric and val is not None:
            stat_txt = f"{stat} = " if stat else ""
            out = f"Found {metric}{id_part} {stat_txt}{val}{unit}"
            return re.sub(r"\s+", " ", out).strip()

    for key in ("evidence", "events", "path", "rows"):
        arr = data.get(key)
        if isinstance(arr, list) and arr:
            first = next((x for x in arr if isinstance(x, dict)), None)
            label = ""
            if first:
                label = str(
                    first.get("label") or first.get("detail") or first.get("kind") or ""
                ).strip()
            noun = {
                "rows": "rows",
                "path": "path steps",
                "events": "events",
            }.get(key, "evidence rows")
            if label:
                return f"{len(arr)} {noun} · {_first_sentence(label, 80)}"
            return f"{len(arr)} {noun}"

    summary = data.get("summary") or data.get("message") or result.get("message")
    if isinstance(summary, str) and summary.strip() and summary.strip().lower() != "ok":
        return _first_sentence(summary)
    return ""


def record_tool_usage(
    usage: Optional[dict],
    *,
    name: str,
    result: Any = None,
) -> Dict[str, Any]:
    """Append one tool call to *usage* (returns a new dict; input untouched)."""
    prev = list(usage["calls"]) if isinstance(usage, dict) and isinstance(usage.get("calls"), list) else []
    n = str(name or "").strip()
    if not n:
        return {"calls": prev}
    category = ai_tool_usage_category(n)
    rec = {
        "name": n,
        "category": category,
        "ok": _result_ok(result),
        "trace_query": category == "Evidence",
        "brief": tool_brief_result(n, result),
    }
    return {"calls": prev + [rec]}


def seed_tool_usage(names: Optional[Sequence[Any]]) -> Dict[str, Any]:
    """Seed *usage* from a list of tool names (no results yet)."""
    out: Dict[str, Any] = {"calls": []}
    for raw in names or []:
        nm = str(raw.get("name") or "") if isinstance(raw, dict) else str(raw or "")
        if nm.strip():
            out = record_tool_usage(out, name=nm)
    return out


def summarize_tool_usage(usage: Optional[dict]) -> Dict[str, Any]:
    """Roll up *usage* into everything the UI shows.

    ``{total, unique, ok, failed, trace_queries,
       by_category: {Evidence, Analysis, Verification, Viewer},
       groups: [{name, category, count, ok, failed, brief}]}``
    """
    calls = usage["calls"] if isinstance(usage, dict) and isinstance(usage.get("calls"), list) else []
    by_category = {"Evidence": 0, "Analysis": 0, "Verification": 0, "Viewer": 0}
    order: List[str] = []
    by_name: Dict[str, Dict[str, Any]] = {}
    ok = 0
    failed = 0
    trace_queries = 0
    for c in calls:
        if not isinstance(c, dict):
            continue
        name = str(c.get("name") or "").strip()
        if not name:
            continue
        category = c.get("category") if c.get("category") in AI_TOOL_USAGE_CATEGORIES \
            else ai_tool_usage_category(name)
        call_ok = c.get("ok") is not False
        if call_ok:
            ok += 1
        else:
            failed += 1
        by_category[category] += 1
        if c.get("trace_query") or category == "Evidence":
            trace_queries += 1
        if name not in by_name:
            order.append(name)
            by_name[name] = {
                "name": name, "category": category,
                "count": 0, "ok": 0, "failed": 0, "brief": "",
            }
        g = by_name[name]
        g["count"] += 1
        if call_ok:
            g["ok"] += 1
        else:
            g["failed"] += 1
        brief = str(c.get("brief") or "").strip()
        if brief:
            g["brief"] = brief
    return {
        "total": len(calls),
        "unique": len(order),
        "ok": ok,
        "failed": failed,
        "trace_queries": trace_queries,
        "by_category": by_category,
        "groups": [by_name[n] for n in order],
    }
