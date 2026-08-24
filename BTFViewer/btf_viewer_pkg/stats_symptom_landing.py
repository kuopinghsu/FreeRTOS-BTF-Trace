"""Statistics symptom landing cards (UX-102).

Lockstep with ``web/src/utils/statsSymptomLanding.js``.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence


SYMPTOM_CARDS: List[Dict[str, Any]] = [
    {
        "id": "unknown",
        "title": "Unknown issue",
        "first_section": "overview",
        "path": ["Analysis Findings", "Timeline Anomalies"],
    },
    {
        "id": "late",
        "title": "Task is sometimes late",
        "first_section": "response_time",
        "path": ["Response Time", "Execution", "Dispatch", "Blocking", "Preemption"],
    },
    {
        "id": "spike",
        "title": "Execution spike / long slice",
        "first_section": "execution",
        "path": ["Execution", "Worst Events", "Preemption Matrix"],
    },
    {
        "id": "dispatch",
        "title": "Dispatch delay",
        "first_section": "dispatch",
        "path": ["Dispatch latency", "Execution", "Core Utilization"],
    },
    {
        "id": "blocking",
        "title": "Blocking / off-CPU wait",
        "first_section": "blocking",
        "path": ["Blocking Time", "Mutex Blocking", "Waiter × Owner"],
    },
    {
        "id": "jitter",
        "title": "Period / jitter",
        "first_section": "period_jitter",
        "path": ["Period / Jitter", "Unified Jitter", "Recurring Patterns"],
    },
    {
        "id": "load",
        "title": "Load imbalance",
        "first_section": "load_balance",
        "path": ["Load Balance", "Task × Core", "Core Utilization"],
    },
    {
        "id": "migration",
        "title": "Migration / thrash",
        "first_section": "migrations",
        "path": ["Core Migrations", "Load Balance", "Task × Core"],
    },
    {
        "id": "sync",
        "title": "Synchronization",
        "first_section": "mutex_blocking",
        "path": ["Mutex Blocking", "Waiter × Owner", "Sync Issues"],
        "requires_sti": True,
    },
    {
        "id": "deadline",
        "title": "Deadline miss",
        "first_section": "deadline",
        "path": ["Deadline / CPU Budget", "Response Time", "Execution"],
    },
]


def symptom_card(card_id: str) -> Optional[Dict[str, Any]]:
    want = str(card_id or "").strip().lower()
    for card in SYMPTOM_CARDS:
        if card.get("id") == want:
            return dict(card)
    return None


def recommend_symptom_from_finding(finding: Optional[Dict[str, Any]]) -> Optional[str]:
    if not isinstance(finding, dict):
        return None
    blob = f"{finding.get('title') or ''} {finding.get('text') or ''}".lower()
    if any(k in blob for k in ("deadline", "budget", "miss")):
        return "deadline"
    if any(k in blob for k in ("migrat", "thrash", "bounce", "affinity")):
        return "migration"
    if any(k in blob for k in ("block", "mutex", "semaphore", "wait")):
        return "blocking"
    if any(k in blob for k in ("jitter", "period", "interval")):
        return "jitter"
    if any(k in blob for k in ("dispatch", "latency", "ready")):
        return "dispatch"
    if any(k in blob for k in ("wcet", "execution", "cpu", "slice")):
        return "spike"
    if any(k in blob for k in ("load", "balance", "gini")):
        return "load"
    if any(k in blob for k in ("response", "late", "slow")):
        return "late"
    return "unknown"


def available_symptom_cards(
    *,
    has_sti: bool = True,
    single_core: bool = False,
) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for card in SYMPTOM_CARDS:
        item = dict(card)
        reasons: List[str] = []
        if card.get("requires_sti") and not has_sti:
            item["disabled"] = True
            reasons.append("STI instrumentation unavailable")
        if card.get("id") == "migration" and single_core:
            item["disabled"] = True
            reasons.append("Single-core trace")
        if reasons:
            item["disabled_reason"] = "; ".join(reasons)
        out.append(item)
    return out


# Desktop/Web section ids used by StatisticsPanel.scroll_to_section / data-section-id.
SYMPTOM_SECTION_MAP: Dict[str, str] = {
    "overview": "anomalies",
    "response_time": "response",
    "execution": "exec",
    "dispatch": "dispatch",
    "blocking": "block",
    "period_jitter": "period",
    "load_balance": "cores",
    "migrations": "migrations",
    "mutex_blocking": "mutex_block",
    "deadline": "deadline",
}


def symptom_section_id(card: Optional[Dict[str, Any]]) -> str:
    if not isinstance(card, dict):
        return "anomalies"
    first = str(card.get("first_section") or "").strip()
    return SYMPTOM_SECTION_MAP.get(first, "anomalies")
