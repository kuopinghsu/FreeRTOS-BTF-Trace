"""Guided first review checklist.

Lockstep with ``web/src/utils/guidedInvestigation.js``.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional


GUIDED_REVIEW_STEPS: List[Dict[str, str]] = [
    {"id": "quality", "label": "Quality", "detail": "Review trace-quality warnings and limitations."},
    {"id": "overview", "label": "Overview", "detail": "Check trace span, tasks, cores, and Full Trace overview."},
    {"id": "symptom", "label": "Symptom", "detail": "Pick a symptom or open Analysis Findings."},
    {"id": "scope", "label": "Scope", "detail": "Place cursors and enable Limit to C1–Cn when needed."},
    {"id": "statistics", "label": "Statistics", "detail": "Read Count, Avg, p95, p99, and Max for the scoped window."},
    {"id": "timeline", "label": "Timeline evidence", "detail": "Use Show on timeline to verify supporting events."},
    {"id": "ai", "label": "AI", "detail": "Investigate or verify using the same Scope."},
    {"id": "result", "label": "Result", "detail": "Export HTML or save your case notes."},
]


def default_guided_progress() -> Dict[str, Any]:
    return {
        "active": False,
        "dismissed": False,
        "step_index": 0,
        "completed": [],
        "trace_key": "",
    }


def guided_step(index: int) -> Optional[Dict[str, str]]:
    if 0 <= int(index) < len(GUIDED_REVIEW_STEPS):
        return dict(GUIDED_REVIEW_STEPS[int(index)])
    return None


def advance_guided_progress(progress: Optional[Dict[str, Any]], step_id: str) -> Dict[str, Any]:
    out = dict(progress or default_guided_progress())
    sid = str(step_id or "").strip()
    done = list(out.get("completed") or [])
    if sid and sid not in done:
        done.append(sid)
    out["completed"] = done
    for i, step in enumerate(GUIDED_REVIEW_STEPS):
        if step["id"] == sid:
            out["step_index"] = min(len(GUIDED_REVIEW_STEPS) - 1, i + 1)
            break
    return out


def format_guided_checklist(progress: Optional[Dict[str, Any]] = None) -> str:
    done = set((progress or {}).get("completed") or [])
    lines = ["Start first review"]
    for step in GUIDED_REVIEW_STEPS:
        mark = "✓" if step["id"] in done else "○"
        lines.append(f"{mark} {step['label']} — {step['detail']}")
    return "\n".join(lines)
