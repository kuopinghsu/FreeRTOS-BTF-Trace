"""Analysis Context strip + stale-result helpers (UX-001 / UX-002).

Lockstep with ``web/src/utils/analysisContext.js``.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence


PANEL_FILTER_LABELS = {
    "statistics": "Statistics filter",
    "ai": "AI context filter",
    "compare": "Compare filter",
    "findings": "Findings filter",
}


def build_analysis_context(
    *,
    trace_name: str = "",
    scope_label: str = "Full Trace",
    scope_duration: str = "",
    filter_labels: Optional[Sequence[str]] = None,
    sample_count: Optional[int] = None,
    cursor_count: int = 0,
    limit_to_cursors: bool = False,
    panel_filter: str = "",
    panel: str = "",
) -> Dict[str, Any]:
    """Normalized context for Findings / Statistics / AI / Compare."""
    filters = [str(x).strip() for x in (filter_labels or []) if str(x).strip()]
    return {
        "trace_name": str(trace_name or "").strip(),
        "scope_label": str(scope_label or "Full Trace").strip() or "Full Trace",
        "scope_duration": str(scope_duration or "").strip(),
        "filter_labels": filters,
        "sample_count": int(sample_count) if sample_count is not None else None,
        "cursor_count": max(0, int(cursor_count or 0)),
        "limit_to_cursors": bool(limit_to_cursors),
        "panel_filter": str(panel_filter or "").strip(),
        "panel": str(panel or "").strip(),
    }


def context_fingerprint(ctx: Optional[Dict[str, Any]]) -> str:
    """Stable key for stale detection (ignores panel-only labels)."""
    if not isinstance(ctx, dict):
        return ""
    parts = [
        ctx.get("trace_name") or "",
        ctx.get("scope_label") or "",
        ctx.get("scope_duration") or "",
        "|".join(ctx.get("filter_labels") or []),
        str(ctx.get("sample_count") if ctx.get("sample_count") is not None else ""),
        str(ctx.get("cursor_count") or 0),
        "1" if ctx.get("limit_to_cursors") else "0",
    ]
    return "\x1f".join(parts)


def is_context_stale(
    snapshot: Optional[Dict[str, Any]],
    current: Optional[Dict[str, Any]],
) -> bool:
    if not isinstance(snapshot, dict) or not snapshot:
        return False
    if not isinstance(current, dict):
        return True
    return context_fingerprint(snapshot) != context_fingerprint(current)


# Short note when cursors exist but Limit to C1–Cn is off (Statistics / plot parity).
CURSORS_NOT_LIMITING_NOTE = "Not limited to cursors"


def format_analysis_context_lines(
    ctx: Optional[Dict[str, Any]],
    *,
    include_panel_filter: bool = True,
    compact: bool = False,
) -> List[str]:
    """Human-readable lines for a context strip or export meta.

    ``compact=True`` (Statistics panel): only the cursor-limit note when needed.
    Scope and Filters are already shown in the Statistics header.
    """
    if not isinstance(ctx, dict):
        return [] if compact else ["Scope: Full Trace"]
    lines: List[str] = []
    cursors_note = (
        int(ctx.get("cursor_count") or 0) >= 2 and not ctx.get("limit_to_cursors")
    )
    if compact:
        if cursors_note:
            lines.append(CURSORS_NOT_LIMITING_NOTE)
        return lines
    trace = str(ctx.get("trace_name") or "").strip()
    if trace:
        lines.append(trace)
    scope = str(ctx.get("scope_label") or "Full Trace")
    dur = str(ctx.get("scope_duration") or "").strip()
    if dur and scope.lower() != "full trace":
        lines.append(f"Scope: {scope} · {dur}")
    else:
        lines.append(f"Scope: {scope}")
    filters = list(ctx.get("filter_labels") or [])
    if filters:
        lines.append("Filters: " + ", ".join(filters))
    n = ctx.get("sample_count")
    if n is not None:
        lines.append(f"Samples: {int(n):,}")
    if cursors_note:
        lines.append(CURSORS_NOT_LIMITING_NOTE)
    if include_panel_filter:
        pf = str(ctx.get("panel_filter") or "").strip()
        panel = str(ctx.get("panel") or "").strip()
        if pf:
            label = PANEL_FILTER_LABELS.get(panel, panel or "Panel filter")
            lines.append(f"{label}: {pf}")
    return lines


def format_analysis_context_strip(
    ctx: Optional[Dict[str, Any]],
    *,
    compact: bool = False,
) -> str:
    return " · ".join(format_analysis_context_lines(ctx, compact=compact))


def format_analysis_context_html(
    ctx: Optional[Dict[str, Any]],
    *,
    compact: bool = False,
) -> str:
    import html as _html

    parts = [
        f'<span class="ctx-line">{_html.escape(line)}</span>'
        for line in format_analysis_context_lines(ctx, compact=compact)
    ]
    return "".join(parts)


def stale_result_banner(*, stale: bool = False) -> Dict[str, str]:
    if not stale:
        return {}
    return {
        "title": "Results may be outdated",
        "message": "Scope or Filters changed since these results were calculated.",
        "action": "Recalculate with current context",
        "live": "polite",
    }
