"""Evidence-strength labels.

Lockstep with ``web/src/utils/evidenceStrength.js``.
Taxonomy from STATISTICS.md: Direct / Derived / Estimated / Configured.
"""
from __future__ import annotations

from typing import Any, Dict, Optional


EVIDENCE_STRENGTHS = ("direct", "derived", "estimated", "configured")

EVIDENCE_STRENGTH_LABELS: Dict[str, str] = {
    "direct": "Direct",
    "derived": "Derived",
    "estimated": "Estimated / heuristic",
    "configured": "Configured comparison",
}

EVIDENCE_STRENGTH_TOOLTIPS: Dict[str, str] = {
    "direct": "Recorded in the trace (slice start/end, core ID, STI tag value).",
    "derived": "Deterministic calculation from recorded evidence.",
    "estimated": "Useful screening evidence with stated assumptions.",
    "configured": "Valid only when the configured threshold matches the application requirement.",
}

# Default strength by Statistics section id (extend as sections ship).
METRIC_EVIDENCE_STRENGTH: Dict[str, str] = {
    "response_time": "estimated",
    "critical_path": "estimated",
    "task_health": "estimated",
    "waiter_owner": "estimated",
    "mutex_blocking": "derived",
    "core_util": "derived",
    "migrations": "derived",
    "load_balance": "derived",
    "deadline": "configured",
    "cpu_budget": "configured",
    "anomalies": "derived",
    "worst_events": "derived",
    "execution": "derived",
    "blocking": "derived",
    "dispatch": "derived",
    "period_jitter": "derived",
    "preemption": "derived",
}

ESTIMATED_VERIFY_HINTS: Dict[str, Dict[str, str]] = {
    "response_time": {
        "missing": "End-to-end response markers or explicit release→complete pairs.",
        "verify": "Correlate Execution, Dispatch, Blocking, and Preemption on the timeline.",
    },
    "critical_path": {
        "missing": "Full causal chain with blocking and preemption evidence.",
        "verify": "Walk Critical Path steps and jump to each blocking/preemption event.",
    },
    "task_health": {
        "missing": "Configured health thresholds and complete slice coverage.",
        "verify": "Compare Task Health with Execution and Blocking tables.",
    },
    "waiter_owner": {
        "missing": "Mutex/semaphore STI pairing for waiter and owner tasks.",
        "verify": "Open Waiter × Owner and Mutex Blocking for the same window.",
    },
    "default": {
        "missing": "Direct trace events that confirm this interpretation.",
        "verify": "Inspect Timeline Evidence and supporting Statistics sections.",
    },
}


def normalize_evidence_strength(value: Any) -> str:
    want = str(value or "").strip().lower()
    if want in EVIDENCE_STRENGTHS:
        return want
    if want in ("heuristic", "estimate"):
        return "estimated"
    if want in ("config", "configured comparison", "budget", "deadline"):
        return "configured"
    return "derived"


def evidence_strength_for_metric(metric_id: str) -> str:
    key = str(metric_id or "").strip().lower().replace("-", "_")
    return METRIC_EVIDENCE_STRENGTH.get(key, "derived")


def evidence_strength_badge(strength: str) -> Dict[str, str]:
    key = normalize_evidence_strength(strength)
    return {
        "strength": key,
        "label": EVIDENCE_STRENGTH_LABELS[key],
        "tooltip": EVIDENCE_STRENGTH_TOOLTIPS[key],
    }


def estimated_verify_hints(metric_id: str = "") -> Dict[str, str]:
    key = str(metric_id or "").strip().lower().replace("-", "_")
    return dict(ESTIMATED_VERIFY_HINTS.get(key) or ESTIMATED_VERIFY_HINTS["default"])


def format_evidence_strength_note(
    strength: str,
    *,
    metric_id: str = "",
    verified: bool = False,
) -> str:
    badge = evidence_strength_badge(strength)
    label = badge["label"]
    if normalize_evidence_strength(strength) == "estimated":
        hints = estimated_verify_hints(metric_id)
        headline = "Cause" if verified else "Possible explanation"
        return (
            f"{label} — {headline}. "
            f"What is missing? {hints['missing']} "
            f"How to verify: {hints['verify']}"
        )
    if verified:
        return f"{label} — verified conclusion."
    return f"{label} — {badge['tooltip']}"
