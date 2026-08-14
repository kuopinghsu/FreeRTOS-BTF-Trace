"""Investigation Case lifecycle: hypotheses, evidence graph, quality, validation.

Host-side (deterministic) layer on top of Analysis Findings / tool results.
Keep behaviour in sync with ``web/src/utils/aiCase.js``.
"""
from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

HYPOTHESIS_STATUSES: Tuple[str, ...] = (
    "supported", "possible", "rejected", "need_evidence",
)
EVIDENCE_QUALITY_BANDS: Tuple[str, ...] = (
    "strong", "medium-high", "medium", "weak", "insufficient",
)
INVESTIGATION_MODES: Tuple[str, ...] = (
    "quick", "diagnose", "compare", "optimize", "report",
)
INVESTIGATION_SCOPE_OPTIONS: Tuple[str, ...] = (
    "execution", "blocking", "migrations", "priority inheritance",
    "nearby events", "findings", "tick",
)
EXPLAIN_LEVELS: Tuple[str, ...] = ("quick", "technical", "deep")
PRIVACY_LEVELS: Tuple[str, ...] = ("local", "cloud_safe", "sensitive")
CASE_SCHEMA = "btf-investigation-case"
CASE_VERSION = 1

_JUMP_RE = re.compile(r"jump:([0-9]+(?:\.[0-9]+)?)", re.IGNORECASE)
_TASK_NAME_RE = re.compile(
    r"\b([A-Za-z][A-Za-z0-9_.-]*\[\d+\])"
)
_METRIC_WORDS = (
    "migrations", "blocking", "execution", "wcet", "latency",
    "priority", "inheritance", "mutex", "tick", "deadline",
    "load", "balance", "preemption", "contention", "dwell",
)
_KNOWN_METRICS = frozenset(_METRIC_WORDS + (
    "priority_inheritance", "sync", "findings", "cpu", "response",
))
_MERMAID_STRIP_RE = re.compile(r'["[\]{}()|]')

_TOOL_REASONS: Dict[str, str] = {
    "detect_anomalies": "Rank Findings as Critical / Warning / Info before drilling in",
    "investigate": "Build hypotheses and an evidence chain for the focus finding",
    "correlate_events": "Check whether blocking, migrations, and sync overlap the spike",
    "query_raw_metric": "Pull a scoped per-task series instead of guessing numbers",
    "find_critical_path": "Walk preempt / block / mutex around the evidence time",
    "detect_priority_inversion": "Test L/M/H inversion as an alternative to contention",
    "search_timeline": "Locate STI / tag / task timestamps like Find",
    "compare_performance": "Measure A vs B deltas instead of narrating them",
    "what_if": "Score a concrete pin / priority / contention experiment",
    "optimize_experiment": "Rank automatic mitigation candidates",
    "explain_finding": "Produce a levelled explanation of the selected finding",
    "interpret_query": "Turn the user's question into an explicit investigation scope",
    "validate_experiment": "Compare expected experiment deltas with a new capture",
    "manage_hypotheses": "Mark a hypothesis supported, rejected, or needing evidence",
}


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(round(float(value)))
    except (TypeError, ValueError):
        return default


def _mermaid_safe_label(text: Any, limit: int = 48) -> str:
    cleaned = _MERMAID_STRIP_RE.sub("", str(text or "").replace("\n", " "))
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return (cleaned or "Node")[:limit]


def empty_investigation_case(
    *,
    question: str = "",
    trace: str = "",
    cursor_lo: Optional[float] = None,
    cursor_hi: Optional[float] = None,
    tasks: Optional[Sequence[str]] = None,
    cores: Optional[Sequence[str]] = None,
) -> Dict[str, Any]:
    """Empty Investigation Case envelope."""
    return {
        "schema": CASE_SCHEMA,
        "version": CASE_VERSION,
        "question": str(question or "").strip(),
        "scope": {
            "trace": str(trace or "").strip(),
            "cursor_lo": cursor_lo,
            "cursor_hi": cursor_hi,
            "tasks": [str(t) for t in (tasks or []) if str(t).strip()],
            "cores": [str(c) for c in (cores or []) if str(c).strip()],
        },
        "suspected_findings": [],
        "hypotheses": [],
        "evidence": [],
        "tools_executed": [],
        "tool_reasons": [],
        "evidence_timeline": [],
        "evidence_graph": {},
        "evidence_quality": {},
        "evidence_coverage": {},
        "falsification": {},
        "confidence": "Medium",
        "confidence_history": [],
        "conclusion": "",
        "alternatives_rejected": [],
        "recommended_action": "",
        "validation": {},
        "mode": "diagnose",
    }


def _finding_blob(finding: Optional[dict]) -> str:
    if not isinstance(finding, dict):
        return ""
    return f"{finding.get('title') or ''} {finding.get('text') or ''}"


def enrich_hypotheses(
    hypotheses: Optional[Sequence[dict]],
    *,
    evidence: Optional[Sequence[dict]] = None,
    alternatives: Optional[Sequence[dict]] = None,
) -> List[Dict[str, Any]]:
    """Attach status / confidence / evidence_count to heuristic hypotheses."""
    ev = [e for e in (evidence or []) if isinstance(e, dict)]
    timed = sum(1 for e in ev if e.get("time") is not None)
    kinds = set()
    for e in ev:
        label = str(e.get("label") or e.get("kind") or "")
        kind = label.split(":", 1)[0].strip().lower() if ":" in label else label.lower()
        if kind:
            kinds.add(kind)
    alt_status = {
        str(a.get("hypothesis") or "").strip().lower(): str(a.get("status") or "").lower()
        for a in (alternatives or []) if isinstance(a, dict)
    }
    out: List[Dict[str, Any]] = []
    for i, raw in enumerate(hypotheses or []):
        if not isinstance(raw, dict):
            continue
        hyp = str(raw.get("hypothesis") or "").strip()
        if not hyp:
            continue
        why = str(raw.get("why") or "").strip()
        status = str(raw.get("status") or "").strip().lower()
        if status not in HYPOTHESIS_STATUSES:
            mapped = alt_status.get(hyp.lower(), "")
            if mapped == "rejected":
                status = "rejected"
            elif mapped == "confirmed" or (i == 0 and timed):
                status = "supported"
            elif i == 0:
                status = "possible"
            elif timed and any(k in hyp.lower() for k in kinds):
                status = "possible"
            else:
                status = "need_evidence"
        if status == "supported":
            conf = 70 + min(25, 8 * timed) - 4 * i
        elif status == "possible":
            conf = 40 + min(20, 5 * timed) - 6 * i
        elif status == "rejected":
            conf = max(5, 18 - 4 * i)
        else:
            conf = 22 - 4 * i
        out.append({
            "id": str(raw.get("id") or f"h{i + 1}"),
            "hypothesis": hyp,
            "why": why,
            "status": status,
            "confidence": max(0, min(100, int(conf))),
            "evidence_count": timed if status in ("supported", "possible") else 0,
        })
    return out


def set_hypothesis_status(
    hypotheses: Sequence[dict],
    hypothesis_id: str,
    status: str,
    *,
    reason: str = "",
) -> List[Dict[str, Any]]:
    """Return a copy with one hypothesis status updated."""
    want = str(hypothesis_id or "").strip().lower()
    st = str(status or "").strip().lower()
    if st not in HYPOTHESIS_STATUSES:
        st = "need_evidence"
    out: List[Dict[str, Any]] = []
    for i, h in enumerate(hypotheses or []):
        if not isinstance(h, dict):
            continue
        item = dict(h)
        hid = str(item.get("id") or f"h{i + 1}").lower()
        name = str(item.get("hypothesis") or "").strip().lower()
        if hid == want or name == want or str(i + 1) == want:
            item["status"] = st
            if reason:
                item["why"] = str(reason).strip()
            if st == "supported":
                item["confidence"] = max(_safe_int(item.get("confidence"), 70), 70)
            elif st == "rejected":
                item["confidence"] = min(_safe_int(item.get("confidence"), 18), 25)
        out.append(item)
    return out


def compare_hypotheses(hypotheses: Sequence[dict]) -> Dict[str, Any]:
    """Rank hypotheses by status then confidence."""
    items = [h for h in (hypotheses or []) if isinstance(h, dict)]
    rank = {"supported": 0, "possible": 1, "need_evidence": 2, "rejected": 3}
    ranked = sorted(
        items,
        key=lambda h: (
            rank.get(str(h.get("status") or ""), 9),
            -_safe_int(h.get("confidence")),
        ),
    )
    leader = ranked[0] if ranked else None
    return {
        "ok": True,
        "ranked": ranked,
        "leader": leader,
        "supported": [h for h in ranked if h.get("status") == "supported"],
        "rejected": [h for h in ranked if h.get("status") == "rejected"],
    }


def build_evidence_graph(
    finding: Optional[dict] = None,
    *,
    evidence: Optional[Sequence[dict]] = None,
    hypotheses: Optional[Sequence[dict]] = None,
    chain: Optional[Sequence[dict]] = None,
) -> Dict[str, Any]:
    """Provenance graph: finding → evidence / chain → hypotheses."""
    nodes: List[Dict[str, Any]] = []
    edges: List[Dict[str, Any]] = []
    fid = "F"
    title = ""
    if isinstance(finding, dict):
        title = str(finding.get("title") or finding.get("id") or "Finding")
        nodes.append({
            "id": fid, "kind": "finding", "label": title,
            "time": None,
        })
    ev_items = [e for e in (evidence or []) if isinstance(e, dict)]
    for i, ev in enumerate(ev_items[:12]):
        nid = f"E{i}"
        nodes.append({
            "id": nid,
            "kind": "evidence",
            "label": str(ev.get("label") or ev.get("kind") or "evidence"),
            "time": ev.get("time"),
        })
        if any(n["id"] == fid for n in nodes):
            edges.append({"from": fid, "to": nid, "rel": "observed"})
    for i, step in enumerate((chain or [])[:8]):
        if not isinstance(step, dict):
            continue
        nid = f"C{i}"
        nodes.append({
            "id": nid,
            "kind": str(step.get("kind") or "step"),
            "label": str(step.get("label") or f"Step {i + 1}"),
            "time": step.get("time"),
        })
        prev = fid if i == 0 and any(n["id"] == fid for n in nodes) else f"C{i - 1}"
        if i == 0 and any(n["id"] == fid for n in nodes):
            edges.append({"from": fid, "to": nid, "rel": "chain"})
        elif i > 0:
            edges.append({"from": prev, "to": nid, "rel": "chain"})
    for j, h in enumerate((hypotheses or [])[:8]):
        if not isinstance(h, dict):
            continue
        nid = f"H{j}"
        status = str(h.get("status") or "possible")
        rel = "supports" if status == "supported" else (
            "contradicts" if status == "rejected" else "hypothesizes"
        )
        nodes.append({
            "id": nid,
            "kind": "hypothesis",
            "label": str(h.get("hypothesis") or f"Hypothesis {j + 1}"),
            "status": status,
            "time": None,
        })
        if any(n["id"] == fid for n in nodes):
            edges.append({"from": fid, "to": nid, "rel": rel})
    return {
        "nodes": nodes,
        "edges": edges,
        "mermaid": evidence_graph_mermaid(nodes, edges),
    }


def evidence_graph_mermaid(
    nodes: Optional[Sequence[dict]] = None,
    edges: Optional[Sequence[dict]] = None,
) -> str:
    items = [n for n in (nodes or []) if isinstance(n, dict) and n.get("id")]
    if not items:
        return ""
    lines = ["graph TD"]
    for n in items:
        nid = str(n.get("id"))
        label = _mermaid_safe_label(n.get("label") or nid)
        kind = str(n.get("kind") or "")
        if kind == "hypothesis":
            lines.append(f"{nid}({label})")
        elif kind == "evidence":
            lines.append(f"{nid}{{{{{label}}}}}")
        else:
            lines.append(f"{nid}[{label}]")
    for e in (edges or []):
        if not isinstance(e, dict):
            continue
        src, dst = str(e.get("from") or ""), str(e.get("to") or "")
        if not src or not dst:
            continue
        rel = str(e.get("rel") or "").strip()
        if rel and rel not in ("observed", "chain"):
            lines.append(f"{src} -- {rel} --> {dst}")
        else:
            lines.append(f"{src} --> {dst}")
    return "\n".join(lines)


def evidence_quality_band(score: Any) -> str:
    """Map a 0–100 heuristic score onto a qualitative band (not a probability)."""
    n = max(0, min(100, _safe_int(score)))
    if n >= 80:
        return "strong"
    if n >= 65:
        return "medium-high"
    if n >= 45:
        return "medium"
    if n >= 25:
        return "weak"
    return "insufficient"


def quality_bar(band: str, width: int = 10) -> str:
    filled_map = {
        "strong": width,
        "medium-high": max(1, int(round(width * 0.8))),
        "medium": max(1, int(round(width * 0.55))),
        "weak": max(1, int(round(width * 0.3))),
        "insufficient": 0,
    }
    filled = filled_map.get(str(band or ""), 0)
    label = {
        "strong": "Strong",
        "medium-high": "Medium-High",
        "medium": "Medium",
        "weak": "Weak",
        "insufficient": "Insufficient",
    }.get(str(band or ""), "Insufficient")
    return "█" * filled + "░" * (width - filled) + f" {label}"


def compute_evidence_quality(
    *,
    score: Any = 0,
    breakdown: Optional[Sequence[dict]] = None,
    evidence: Optional[Sequence[dict]] = None,
    alternatives: Optional[Sequence[dict]] = None,
    checks: Optional[Sequence[dict]] = None,
    evidence_chain: str = "",
) -> Dict[str, Any]:
    """Qualitative Evidence Quality (heuristic, not a statistical CI)."""
    ev = [e for e in (evidence or []) if isinstance(e, dict)]
    alts = [a for a in (alternatives or []) if isinstance(a, dict)]
    chks = [c for c in (checks or []) if isinstance(c, dict)]
    has_direct = any(e.get("time") is not None for e in ev)
    kinds = set()
    for e in ev:
        label = str(e.get("label") or "")
        if ":" in label:
            kind = label.split(":", 1)[0].strip().lower()
            if kind:
                kinds.add(kind)
    has_timeline = len(kinds) >= 2 or bool(str(evidence_chain or "").strip())
    has_metric = bool(chks)
    untested = [
        a for a in alts
        if str(a.get("status") or "").lower() in ("untested", "need_evidence", "")
    ]
    alt_mark = "yes" if alts and not untested else ("partial" if alts else "no")
    band = evidence_quality_band(score)
    flags = {
        "direct_evidence": has_direct,
        "timeline_correlation": has_timeline,
        "metric_correlation": has_metric,
        "alternative_tested": alt_mark,
    }
    return {
        "band": band,
        "bar": quality_bar(band),
        "score": max(0, min(100, _safe_int(score))),
        "label": "Evidence Quality",
        "flags": flags,
        "breakdown": list(breakdown or []),
        "confidence_label": {
            "strong": "High",
            "medium-high": "Medium-High",
            "medium": "Medium",
            "weak": "Low",
            "insufficient": "Low",
        }.get(band, "Low"),
    }


def compute_evidence_coverage(
    *,
    claims: Optional[Sequence[dict]] = None,
    evidence: Optional[Sequence[dict]] = None,
    known_tasks: Optional[Sequence[str]] = None,
    known_metrics: Optional[Sequence[str]] = None,
) -> Dict[str, Any]:
    """Fraction of extracted claims that are grounded in evidence / known names."""
    claim_items = [c for c in (claims or []) if isinstance(c, dict)]
    ev = [e for e in (evidence or []) if isinstance(e, dict)]
    tasks = {str(t).strip().lower() for t in (known_tasks or []) if str(t).strip()}
    metrics = {
        str(m).strip().lower() for m in (known_metrics or _KNOWN_METRICS) if str(m).strip()
    }
    timed = {e.get("time") for e in ev if e.get("time") is not None}
    total = len(claim_items) or 0
    observed = 0
    timeline = 0
    metric_ok = 0
    unverified = 0
    for c in claim_items:
        kind = str(c.get("kind") or "")
        ok = bool(c.get("ok"))
        if kind in ("timestamp", "jump"):
            if ok or c.get("value") in timed:
                timeline += 1
                observed += 1
            else:
                unverified += 1
        elif kind == "task":
            name = str(c.get("value") or "").strip().lower()
            if ok or name in tasks:
                observed += 1
            else:
                unverified += 1
        elif kind == "metric":
            name = str(c.get("value") or "").strip().lower()
            if ok or name in metrics:
                metric_ok += 1
                observed += 1
            else:
                unverified += 1
        else:
            if ok:
                observed += 1
            else:
                unverified += 1
    denom = total or 1
    pct = int(round(100.0 * observed / denom)) if total else (100 if ev else 0)
    if not claim_items and ev:
        observed = min(len(ev), 7)
        total = max(len(ev), 7)
        timeline = sum(1 for e in ev if e.get("time") is not None)
        pct = int(round(100.0 * min(1.0, observed / max(total, 1))))
    return {
        "percent": max(0, min(100, pct)),
        "bar": (
            "█" * max(0, min(10, int(round(10 * max(0, min(100, pct)) / 100.0))))
            + "░" * (10 - max(0, min(10, int(round(10 * max(0, min(100, pct)) / 100.0)))))
            + f" {max(0, min(100, pct))}%"
        ),
        "directly_observed": f"{observed}/{total or observed}",
        "timeline_verified": timeline,
        "metric_verified": metric_ok,
        "unverified_assumptions": unverified,
        "claims": total,
    }


def _quality_flag_mark(value: Any) -> str:
    if value is True or str(value).lower() in ("yes", "true", "1"):
        return "✓"
    if str(value).lower() in ("partial", "triangle", "maybe"):
        return "△"
    return "○"


def format_quality_flag_lines(
    quality: Optional[dict] = None,
    labels: Optional[Dict[str, str]] = None,
) -> List[str]:
    """Checklist under Evidence Quality (direct / timeline / metric / alternative)."""
    lab = labels if isinstance(labels, dict) else {}
    flags = (quality or {}).get("flags") if isinstance(quality, dict) else {}
    flags = flags if isinstance(flags, dict) else {}
    rows = (
        ("direct_evidence", "quality_direct", "Direct evidence"),
        ("timeline_correlation", "quality_timeline", "Timeline correlation"),
        ("metric_correlation", "quality_metric", "Metric correlation"),
        ("alternative_tested", "quality_alternative", "Alternative tested"),
    )
    return [
        f"- {lab.get(lk, fallback)} {_quality_flag_mark(flags.get(fk))}"
        for fk, lk, fallback in rows
    ]


def format_coverage_count_lines(
    coverage: Optional[dict] = None,
    labels: Optional[Dict[str, str]] = None,
) -> List[str]:
    """5/7-style breakdown under Evidence Coverage."""
    lab = labels if isinstance(labels, dict) else {}
    cov = coverage if isinstance(coverage, dict) else {}
    claims = cov.get("claims")
    observed = cov.get("directly_observed")
    timeline = cov.get("timeline_verified")
    metric = cov.get("metric_verified")
    unverified = cov.get("unverified_assumptions")
    if observed is None and claims is None:
        return []
    denom = f"/{claims}" if claims not in (None, "") else ""
    return [
        f"- {lab.get('coverage_observed', 'Directly observed')} {observed}",
        f"- {lab.get('coverage_timeline', 'Timeline verified')} "
        f"{timeline}{denom if not str(timeline).count('/') else ''}",
        f"- {lab.get('coverage_metric', 'Metric verified')} "
        f"{metric}{denom if not str(metric).count('/') else ''}",
        f"- {lab.get('coverage_unverified', 'Unverified assumptions')} {unverified}",
    ]


def should_confirm_interpreted_query(
    query: str = "",
    *,
    template_id: str = "",
    already_interpreted: bool = False,
) -> bool:
    """True when a free-form Ask should show the interpret/scope card first."""
    if already_interpreted or str(template_id or "").strip():
        return False
    q = str(query or "").strip()
    if not q:
        return False
    if "Investigation scope:" in q and "Interpreted as " in q:
        return False
    return True


_COMPARE_PERCENT_ALIASES: Dict[str, str] = {
    "migrations": "migrations",
    "migrated_tasks": "migrations",
    "blocking": "blocking",
    "execution": "execution",
}


def experiment_percents_from_compare(compare: Optional[dict] = None) -> Dict[str, float]:
    """Extract metric → signed percent from compare_performance / Trace Compare."""
    data = compare if isinstance(compare, dict) else {}
    if isinstance(data.get("data"), dict) and not data.get("checks"):
        data = data["data"]
    out: Dict[str, float] = {}

    def _store(raw_key: Any, pct: Any) -> None:
        try:
            value = float(pct)
        except (TypeError, ValueError):
            return
        key = str(raw_key or "").strip().lower().replace(" ", "_")
        if not key:
            return
        alias = _COMPARE_PERCENT_ALIASES.get(key, key)
        out[alias] = value
        if alias != key:
            out[key] = value

    for c in data.get("checks") or []:
        if not isinstance(c, dict):
            continue
        mid = str(c.get("id") or c.get("metric") or "").strip()
        label = str(c.get("label") or "").lower()
        if not mid:
            if "migrat" in label:
                mid = "migrations"
            elif "block" in label:
                mid = "blocking"
            elif "execut" in label:
                mid = "execution"
        detail = str(c.get("detail") or "")
        delta = c.get("delta")
        if delta is None:
            continue
        if "%" in detail:
            _store(mid, delta)
            continue
        try:
            cand = float(c.get("candidate"))
            base = float(c.get("baseline"))
        except (TypeError, ValueError):
            continue
        if base:
            _store(mid, 100.0 * (cand - base) / abs(base))
    for r in data.get("rows") or []:
        if not isinstance(r, dict) or r.get("delta_pct") is None:
            continue
        metric = str(r.get("metric") or "")
        field = str(r.get("field") or "")
        if field and field not in ("count", "total", ""):
            continue
        _store(metric, r.get("delta_pct"))
    return out


_ANNOTATION_LINE_RE = re.compile(
    r"(?im)^(?:annotation|note|mark)\s*[:=]\s*.+$"
)
_ANNOTATION_INLINE_RE = re.compile(
    r'(?i)\b(?:annotation|note)\s*(?:[:=]\s*|"\s*)"[^"]*"'
)


def sanitize_annotations_text(text: str) -> str:
    """Strip annotation note payloads before a cloud send."""
    out = _ANNOTATION_LINE_RE.sub("[annotation]", str(text or ""))
    return _ANNOTATION_INLINE_RE.sub("[annotation]", out)


def falsification_checks(finding: Optional[dict] = None) -> Dict[str, Any]:
    """What evidence would disprove the leading explanation for this finding."""
    blob = _finding_blob(finding).lower()
    title = str((finding or {}).get("title") or "this finding") if finding else "the conclusion"
    checks: List[str] = []
    next_check = "Inspect the strongest jump:TIME on the timeline"
    if "migrat" in blob or "thrash" in blob or "bounc" in blob:
        checks = [
            "No core-to-core hops in the cursor window for the named task",
            "Ping-pong / bounce count is near zero in the scoped Statistics",
            "Another task accounts for the majority of migrations",
        ]
        next_check = "Open Core Migrations / Heatmap around the cited jump:TIME"
    elif "block" in blob or "latency" in blob or "mutex" in blob or "contention" in blob:
        checks = [
            "No corresponding mutex hold episode in the window",
            "Latency spike occurs while the task is runnable (on-CPU)",
            "Another task causes the majority of blocking",
        ]
        next_check = "Inspect mutex hold / Blocking Max around the cited jump:TIME"
    elif "inversion" in blob or "inherit" in blob:
        checks = [
            "No L/M/H geometry or inherit episode in the window",
            "The waiter is not blocked on the suspected mutex",
            "Priority boost duration does not overlap the latency spike",
        ]
        next_check = "Open Priority Inheritance around the cited jump:TIME"
    elif "wcet" in blob or "execution" in blob or "spike" in blob:
        checks = [
            "Max execution slice is in-family with typical (no Max≫Avg)",
            "The long slice is an ISR / TICK, not the named task",
            "Preemption, not payload, stretches the slice",
        ]
        next_check = "Jump to Execution Max and confirm the task row"
    elif "tick" in blob or "missed" in blob:
        checks = [
            "Tick CV is below the 5% threshold in this scope",
            "Large gaps are idle (tickless), not missed ticks under load",
        ]
        next_check = "Open Trace Health (TICK) for the scoped window"
    elif "load" in blob or "imbalance" in blob or "balance" in blob:
        checks = [
            "Load Balance Score is in the green zone for this window",
            "Concurrent-active distribution is even across cores",
        ]
        next_check = "Open Core Utilisation / Load Balance Score"
    else:
        checks = [
            "Cited jump:TIME is outside the cursor region",
            "Named task does not appear in scoped Statistics",
            "The metric named in the conclusion is not present",
        ]
    return {
        "conclusion": title,
        "would_disprove": checks,
        "disprove": checks,
        "supporting": [],
        "next_check": next_check,
    }


def extract_claims(
    text: str,
    *,
    known_tasks: Optional[Sequence[str]] = None,
    known_metrics: Optional[Sequence[str]] = None,
    cursor_lo: Optional[float] = None,
    cursor_hi: Optional[float] = None,
) -> List[Dict[str, Any]]:
    """Pull task names, metrics, and jump:TIME values out of a reply."""
    src = str(text or "")
    tasks = {str(t).strip() for t in (known_tasks or []) if str(t).strip()}
    tasks_l = {t.lower(): t for t in tasks}
    metrics = {
        str(m).strip().lower() for m in (known_metrics or _KNOWN_METRICS) if str(m).strip()
    }
    claims: List[Dict[str, Any]] = []
    seen: set = set()

    def add(kind: str, value: Any, *, ok: bool, detail: str = "") -> None:
        key = (kind, str(value))
        if key in seen:
            return
        seen.add(key)
        claims.append({"kind": kind, "value": value, "ok": ok, "detail": detail})

    for m in _JUMP_RE.finditer(src):
        try:
            t = float(m.group(1))
        except ValueError:
            continue
        in_scope = True
        detail = ""
        if cursor_lo is not None and t < float(cursor_lo):
            in_scope = False
            detail = "timestamp before cursor window"
        if cursor_hi is not None and t > float(cursor_hi):
            in_scope = False
            detail = "timestamp after cursor window"
        add("jump", t, ok=in_scope, detail=detail)

    for m in _TASK_NAME_RE.finditer(src):
        name = m.group(1)
        if tasks:
            ok = name.lower() in tasks_l
            add("task", name, ok=ok, detail="" if ok else "task not in trace/findings")
        else:
            add("task", name, ok=True, detail="no known-task list; accepted")

    low = src.lower()
    for metric in sorted(metrics):
        if re.search(r"\b" + re.escape(metric) + r"\b", low):
            add("metric", metric, ok=True)

    return claims


def validate_ai_response(
    text: str,
    *,
    known_tasks: Optional[Sequence[str]] = None,
    known_metrics: Optional[Sequence[str]] = None,
    known_times: Optional[Sequence[float]] = None,
    cursor_lo: Optional[float] = None,
    cursor_hi: Optional[float] = None,
    tool_results: Optional[Sequence[dict]] = None,
    allow_estimates: bool = True,
) -> Dict[str, Any]:
    """Host-side hallucination guard for an assistant reply."""
    claims = extract_claims(
        text,
        known_tasks=known_tasks,
        known_metrics=known_metrics,
        cursor_lo=cursor_lo,
        cursor_hi=cursor_hi,
    )
    times = set()
    for t in known_times or []:
        try:
            times.add(float(t))
        except (TypeError, ValueError):
            continue
    for res in tool_results or []:
        if not isinstance(res, dict):
            continue
        data = res.get("data") if isinstance(res.get("data"), dict) else res
        for key in ("evidence", "events", "path"):
            for item in data.get(key) or []:
                if isinstance(item, dict) and item.get("time") is not None:
                    try:
                        times.add(float(item.get("time")))
                    except (TypeError, ValueError):
                        continue
    flags: List[str] = []
    unverified = 0
    for c in claims:
        if c.get("kind") == "jump" and times:
            try:
                val = float(c.get("value"))
            except (TypeError, ValueError):
                continue
            if val not in times and not any(abs(val - t) < 1e-6 for t in times):
                # Still ok if it is inside the cursor window and tools didn't
                # enumerate every timestamp — only flag when out of scope.
                if not c.get("ok"):
                    unverified += 1
                    flags.append(f"jump:{c['value']} outside cursor window")
        elif c.get("kind") == "task" and not c.get("ok"):
            unverified += 1
            flags.append(f"unknown task {c.get('value')}")
        elif not c.get("ok"):
            unverified += 1
            flags.append(str(c.get("detail") or c.get("kind")))
    low = str(text or "").lower()
    if not allow_estimates:
        if "what_if" in low or "optimize_experiment" in low:
            if "estimate" not in low and "heuristic" not in low:
                flags.append("simulator result not labelled as an estimate")
                unverified += 1
    ok = unverified == 0
    return {
        "ok": ok,
        "claims": claims,
        "unverified": unverified,
        "flags": flags,
        "message": (
            "All extracted claims match trace scope"
            if ok else
            f"{unverified} claim(s) could not be verified against trace data"
        ),
    }


def interpret_investigation_query(
    question: str,
    *,
    findings: Optional[Sequence[dict]] = None,
    cursor_lo: Optional[float] = None,
    cursor_hi: Optional[float] = None,
) -> Dict[str, Any]:
    """Turn a free-form question into an explicit investigation scope."""
    q = str(question or "").strip()
    blob = q.lower()
    items = [f for f in (findings or []) if isinstance(f, dict)]
    kind = "diagnose"
    scopes = ["execution", "blocking"]
    if any(w in blob for w in ("compar", "regress", "vs ", "versus", "before", "after")):
        kind = "compare"
        scopes = ["execution", "blocking", "migrations", "tick"]
    elif any(w in blob for w in ("optimi", "faster", "improve", "what-if", "what if", "pin")):
        kind = "optimize"
        scopes = ["migrations", "blocking", "execution"]
    elif any(w in blob for w in ("report", "write-up", "summary for")):
        kind = "report"
        scopes = ["findings"]
    elif any(w in blob for w in ("why", "cause", "root", "investigat", "slow")):
        kind = "diagnose"
        scopes = ["execution", "blocking", "migrations", "priority inheritance"]
    elif any(w in blob for w in ("what", "explain", "triage")):
        kind = "quick"
        scopes = ["findings"]
    if "migrat" in blob or "thrash" in blob:
        if "migrations" not in scopes:
            scopes.append("migrations")
    if "mutex" in blob or "lock" in blob or "invert" in blob:
        if "priority inheritance" not in scopes:
            scopes.append("priority inheritance")
    focus = None
    if items:
        focus = items[0]
        qlow = blob
        for f in items:
            title = str(f.get("title") or "").lower()
            task = str(f.get("task") or "").lower()
            if title and title in qlow:
                focus = f
                break
            if task and task in qlow:
                focus = f
                break
    window = None
    if cursor_lo is not None and cursor_hi is not None:
        window = {"lo": cursor_lo, "hi": cursor_hi}
    mode = kind if kind in INVESTIGATION_MODES else "diagnose"
    return {
        "ok": True,
        "interpreted_question": q or "Investigate the main performance problem",
        "kind": kind,
        "mode": mode,
        "scope": scopes,
        "finding_id": str((focus or {}).get("id") or ""),
        "task": str((focus or {}).get("task") or ""),
        "cursor_window": window,
        "suggested_tools": investigation_mode_plan(mode).get("tools") or [],
        "message": f"Interpreted as {kind} investigation",
    }


def explain_finding_payload(
    finding: Optional[dict],
    *,
    level: str = "technical",
    hypotheses: Optional[Sequence[dict]] = None,
) -> Dict[str, Any]:
    """Three-level explanation of one Analysis Finding (host-side)."""
    lv = str(level or "technical").strip().lower()
    if lv not in EXPLAIN_LEVELS:
        lv = "technical"
    if not isinstance(finding, dict):
        return {"ok": False, "message": "No finding selected", "level": lv}
    title = str(finding.get("title") or finding.get("id") or "Finding")
    text = str(finding.get("text") or "")
    sev = str(finding.get("severity") or "info")
    task = str(finding.get("task") or "")
    hyps = enrich_hypotheses(hypotheses or [], evidence=finding.get("evidence") or [])
    quick = f"{sev.upper()}: {title}." + (f" Focus task {task}." if task else "")
    technical = (
        f"{title} ({sev}). {text} "
        "Confirm the named Statistics section, then click Max / a scatter "
        "point to seek the timeline."
    ).strip()
    deep = technical
    if hyps:
        names = "; ".join(
            f"{h['hypothesis']} [{h['status']}]" for h in hyps[:4]
        )
        deep = (
            f"{technical} Leading hypotheses: {names}. "
            "Call investigate → correlate_events → find_critical_path, "
            "then verify jump:TIME inside the cursor window."
        )
    body = {"quick": quick, "technical": technical, "deep": deep}[lv]
    return {
        "ok": True,
        "message": f"{lv} explanation of {finding.get('id') or title}",
        "level": lv,
        "finding": {
            "id": finding.get("id"),
            "severity": sev,
            "title": title,
            "text": text,
            "task": task,
            "evidence": list(finding.get("evidence") or []),
        },
        "hypotheses": hyps,
        "explanation": body,
        "levels": {
            "quick": quick,
            "technical": technical,
            "deep": deep,
        },
    }


def investigation_mode_plan(mode: str = "diagnose") -> Dict[str, Any]:
    """User-facing investigation mode → goal + tool sequence."""
    want = str(mode or "diagnose").strip().lower()
    if want not in INVESTIGATION_MODES:
        want = "diagnose"
    plans = {
        "quick": {
            "goal": "Find the most likely problem",
            "tools": ["detect_anomalies", "investigate"],
            "template": "triage",
        },
        "diagnose": {
            "goal": "Find cause → gather evidence → verify",
            "tools": [
                "investigate", "correlate_events", "find_critical_path",
            ],
            "template": "investigate",
        },
        "compare": {
            "goal": "Explain why A differs from B",
            "tools": ["compare_performance", "regression_explain"],
            "template": "compare",
        },
        "optimize": {
            "goal": "Find cause → propose experiments → rank them",
            "tools": [
                "investigate", "what_if", "optimize_experiment",
                "recommend_experiments",
            ],
            "template": "optimize",
        },
        "report": {
            "goal": "Turn confirmed findings into an engineering report",
            "tools": ["generate_report", "export_report"],
            "template": "diagnostic_report",
        },
    }
    plan = dict(plans[want])
    plan["mode"] = want
    plan["ok"] = True
    return plan


INVESTIGATION_MODE_LABELS: Dict[str, str] = {
    "quick": "Quick",
    "diagnose": "Diagnose",
    "compare": "Compare",
    "optimize": "Optimize",
    "report": "Report",
}


def investigation_mode_prompt(mode: str = "diagnose") -> str:
    """User prompt for an Investigation Mode chip (maps onto existing tools)."""
    plan = investigation_mode_plan(mode)
    listed = " → ".join(str(t) for t in (plan.get("tools") or []) if t)
    label = INVESTIGATION_MODE_LABELS.get(plan["mode"], plan["mode"])
    return (
        f"{plan.get('goal') or label}. Call these tools in order: {listed}. "
        "After each tool, update hypotheses with manage_hypotheses when the "
        "status changes. Finish with a verdict, jump:TIME evidence, "
        "what would disprove this, confidence, and one next check."
    )


def parse_user_investigation_templates(raw: Any) -> List[Dict[str, Any]]:
    """Deserialize user-saved investigation sequences."""
    if isinstance(raw, list):
        items = raw
    else:
        try:
            items = json.loads(str(raw or "") or "[]")
        except json.JSONDecodeError:
            return []
    out: List[Dict[str, Any]] = []
    if not isinstance(items, list):
        return out
    for i, it in enumerate(items):
        if not isinstance(it, dict):
            continue
        label = str(it.get("label") or "").strip()
        steps = [str(s).strip() for s in (it.get("steps") or []) if str(s).strip()]
        if not label or not steps:
            continue
        tid = str(it.get("id") or "").strip()
        if not tid:
            tid = re.sub(r"[^a-z0-9]+", "_", label.lower()).strip("_") or f"user_{i + 1}"
        out.append({
            "id": tid, "label": label, "steps": steps, "user": True,
        })
    return out


def dump_user_investigation_templates(items: Optional[Sequence[dict]] = None) -> str:
    rows = []
    for it in items or []:
        if not isinstance(it, dict):
            continue
        label = str(it.get("label") or "").strip()
        steps = [str(s).strip() for s in (it.get("steps") or []) if str(s).strip()]
        if not label or not steps:
            continue
        tid = str(it.get("id") or "").strip() or re.sub(
            r"[^a-z0-9]+", "_", label.lower()).strip("_")
        rows.append({"id": tid, "label": label, "steps": steps})
    return json.dumps(rows, ensure_ascii=False)


def new_user_investigation_template(
    label: str,
    steps: Optional[Sequence[str]] = None,
) -> Dict[str, Any]:
    name = str(label or "").strip() or "My Investigation"
    seq = [str(s).strip() for s in (steps or []) if str(s).strip()]
    if not seq:
        seq = list(investigation_mode_plan("diagnose").get("tools") or ["investigate"])
    tid = re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_") or "user"
    return {"id": tid, "label": name, "steps": seq, "user": True}


VALIDATE_EXPERIMENT_PROMPT = (
    "Did this before/after capture validate the experiment? "
    "Call validate_experiment. Omit actual — the host fills percents from "
    "the last Trace Compare (Scope to cursors honored). If expected deltas "
    "are known from what_if or optimize_experiment, pass them as expected; "
    "otherwise omit expected. Then report VALIDATED, PARTIALLY VALIDATED, "
    "or DISPROVED with supporting evidence and one next check."
)


def validate_experiment(
    expected: Optional[dict] = None,
    actual: Optional[dict] = None,
) -> Dict[str, Any]:
    """Compare expected experiment deltas with Trace Compare / what-if actuals.

    *expected* / *actual* maps metric → signed percent (negative = improvement
    for cost-like metrics such as migrations / blocking).
    """
    exp = expected if isinstance(expected, dict) else {}
    act = actual if isinstance(actual, dict) else {}
    rows: List[Dict[str, Any]] = []
    matched = 0
    disagreed = 0
    for key in sorted(set(list(exp.keys()) + list(act.keys()))):
        e = exp.get(key)
        a = act.get(key)
        try:
            e_n = float(e) if e is not None else None
        except (TypeError, ValueError):
            e_n = None
        try:
            a_n = float(a) if a is not None else None
        except (TypeError, ValueError):
            a_n = None
        status = "missing"
        if e_n is None and a_n is None:
            status = "missing"
        elif e_n is None:
            status = "unspecified"
        elif a_n is None:
            status = "unmeasured"
        else:
            same_dir = (e_n == 0 and abs(a_n) < 5) or (e_n * a_n > 0) or (
                abs(e_n) < 5 and abs(a_n) < 8
            )
            close = abs(a_n - e_n) <= max(10.0, abs(e_n) * 0.5)
            if same_dir and close:
                status = "validated"
                matched += 1
            elif same_dir:
                status = "partial"
                matched += 1
            else:
                status = "disproved"
                disagreed += 1
        rows.append({
            "metric": str(key),
            "expected": e_n,
            "actual": a_n,
            "status": status,
        })
    if not rows:
        result = "INCONCLUSIVE"
    elif disagreed and matched:
        result = "PARTIALLY VALIDATED"
    elif disagreed:
        result = "DISPROVED"
    elif matched:
        result = "VALIDATED"
    else:
        result = "INCONCLUSIVE"
    return {
        "ok": True,
        "result": result,
        "rows": rows,
        "matched": matched,
        "disagreed": disagreed,
        "message": f"Experiment {result}",
    }


def record_confidence_step(
    history: Optional[Sequence[dict]],
    *,
    tool_name: str,
    score: Any = None,
    band: str = "",
    note: str = "",
) -> List[Dict[str, Any]]:
    """Append one confidence-evolution step (audit trail)."""
    out = [dict(s) for s in (history or []) if isinstance(s, dict)]
    entry: Dict[str, Any] = {
        "tool": str(tool_name or "").strip(),
        "note": str(note or "").strip(),
    }
    if score is not None:
        entry["score"] = max(0, min(100, _safe_int(score)))
        entry["band"] = band or evidence_quality_band(score)
    elif band:
        entry["band"] = band
    out.append(entry)
    return out


def format_confidence_evolution(history: Optional[Sequence[dict]]) -> str:
    lines: List[str] = []
    for i, step in enumerate(history or []):
        if not isinstance(step, dict):
            continue
        tool = str(step.get("tool") or f"step {i + 1}")
        if i == 0:
            prefix = "Initial"
        else:
            prefix = f"After {tool}"
        band = str(step.get("band") or "")
        score = step.get("score")
        extra = f" {score}%" if score is not None else ""
        note = str(step.get("note") or "")
        label = f"{prefix}: {band}{extra}".strip()
        if note:
            label += f" — {note}"
        lines.append(label)
    return "\n".join(lines)


def tool_call_reason(tool_name: str, finding: Optional[dict] = None) -> str:
    """Why the host / model would call this tool for the current finding."""
    name = str(tool_name or "").strip()
    base = _TOOL_REASONS.get(name, f"Run {name} as part of the investigation plan")
    blob = _finding_blob(finding)
    if blob:
        title = str((finding or {}).get("title") or "").strip()
        if title:
            return f"{base}. Finding: {title}."
    return base


def empty_cost_meter() -> Dict[str, Any]:
    return {
        "prompt_tokens": 0,
        "completion_tokens": 0,
        "total_tokens": 0,
        "tool_calls": 0,
        "trace_queries": 0,
        "model_time_s": 0.0,
        "estimated_usd": 0.0,
    }


def accumulate_cost(
    meter: Optional[dict],
    *,
    prompt_tokens: int = 0,
    completion_tokens: int = 0,
    tool_calls: int = 0,
    trace_queries: int = 0,
    model_time_s: float = 0.0,
    usd_per_1k: float = 0.0,
) -> Dict[str, Any]:
    out = dict(meter or empty_cost_meter())
    pt = max(0, _safe_int(prompt_tokens))
    ct = max(0, _safe_int(completion_tokens))
    out["prompt_tokens"] = _safe_int(out.get("prompt_tokens")) + pt
    out["completion_tokens"] = _safe_int(out.get("completion_tokens")) + ct
    out["total_tokens"] = out["prompt_tokens"] + out["completion_tokens"]
    out["tool_calls"] = _safe_int(out.get("tool_calls")) + max(0, _safe_int(tool_calls))
    out["trace_queries"] = _safe_int(out.get("trace_queries")) + max(
        0, _safe_int(trace_queries))
    try:
        out["model_time_s"] = round(
            float(out.get("model_time_s") or 0) + max(0.0, float(model_time_s or 0)),
            3,
        )
    except (TypeError, ValueError):
        pass
    added = (pt + ct) / 1000.0 * max(0.0, float(usd_per_1k or 0))
    try:
        out["estimated_usd"] = round(float(out.get("estimated_usd") or 0) + added, 6)
    except (TypeError, ValueError):
        out["estimated_usd"] = round(added, 6)
    return out


def format_cost_meter(meter: Optional[dict]) -> str:
    m = meter if isinstance(meter, dict) else empty_cost_meter()
    usd = float(m.get("estimated_usd") or 0)
    usd_s = f"${usd:.3f}" if usd else "—"
    return (
        f"Context {m.get('total_tokens') or 0} tokens · "
        f"Tool calls {m.get('tool_calls') or 0} · "
        f"Trace queries {m.get('trace_queries') or 0} · "
        f"Model time {m.get('model_time_s') or 0}s · "
        f"Est. {usd_s}"
    )


def _format_token_count(n: Any) -> str:
    try:
        count = int(n or 0)
    except (TypeError, ValueError):
        count = 0
    if count >= 1000:
        compact = f"{count / 1000.0:.1f}".rstrip("0").rstrip(".")
        return f"{compact}k"
    return str(count)


def format_cost_status(meter: Optional[dict]) -> str:
    """One-line status suffix: ``1.3k tok · 2 tools · 1.5s``."""
    m = meter if isinstance(meter, dict) else empty_cost_meter()
    try:
        tokens = int(m.get("total_tokens") or 0)
    except (TypeError, ValueError):
        tokens = 0
    try:
        tools = int(m.get("tool_calls") or 0)
    except (TypeError, ValueError):
        tools = 0
    try:
        time_s = float(m.get("model_time_s") or 0)
    except (TypeError, ValueError):
        time_s = 0.0
    try:
        usd = float(m.get("estimated_usd") or 0)
    except (TypeError, ValueError):
        usd = 0.0
    parts = [f"{_format_token_count(tokens)} tok"]
    if tools:
        parts.append(f"{tools} tools")
    if time_s:
        parts.append(f"{time_s:g}s")
    if usd:
        parts.append(f"${usd:.3f}")
    return " · ".join(parts)


def cost_meter_active(meter: Optional[dict]) -> bool:
    """True when the conversation has accumulated any billable usage."""
    m = meter if isinstance(meter, dict) else empty_cost_meter()
    try:
        tokens = int(m.get("total_tokens") or 0)
    except (TypeError, ValueError):
        tokens = 0
    try:
        tools = int(m.get("tool_calls") or 0)
    except (TypeError, ValueError):
        tools = 0
    try:
        time_s = float(m.get("model_time_s") or 0)
    except (TypeError, ValueError):
        time_s = 0.0
    try:
        usd = float(m.get("estimated_usd") or 0)
    except (TypeError, ValueError):
        usd = 0.0
    return tokens > 0 or tools > 0 or time_s > 0 or usd > 0


def status_with_cost(message: str, meter: Optional[dict] = None) -> str:
    """Append the cost line to an AI status message when usage exists."""
    text = str(message or "").strip()
    if not cost_meter_active(meter):
        return text
    cost = format_cost_status(meter)
    return f"{text} · {cost}" if text else cost


def chat_usage_from_response(body: Any) -> Dict[str, int]:
    """Normalize OpenAI / Gemini ``usage`` objects into token counts."""
    usage = body.get("usage") if isinstance(body, dict) else None
    if not isinstance(usage, dict):
        return {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
    pt = _safe_int(
        usage.get("prompt_tokens") or usage.get("prompt_token_count") or 0)
    ct = _safe_int(
        usage.get("completion_tokens")
        or usage.get("completion_token_count")
        or usage.get("candidates_token_count")
        or 0
    )
    tot = _safe_int(usage.get("total_tokens") or (pt + ct))
    return {"prompt_tokens": pt, "completion_tokens": ct, "total_tokens": tot}


def format_privacy_chip(priv: Optional[dict] = None) -> str:
    level = str((priv or {}).get("level") or "local")
    return {
        "local": "🟢 Local",
        "cloud_safe": "🟡 Cloud",
        "sensitive": "🔴 Sensitive",
    }.get(level, level.replace("_", " ").title())


def investigation_template_prompt(template: Optional[dict] = None) -> str:
    tpl = template if isinstance(template, dict) else {}
    label = str(tpl.get("label") or "Investigation")
    steps = [str(s) for s in (tpl.get("steps") or []) if s]
    listed = " → ".join(steps) if steps else "investigate"
    return (
        f"Run the {label}. Call these tools in order: {listed}. "
        "After each tool, update hypotheses with manage_hypotheses when the "
        "status changes. Finish with a verdict, jump:TIME evidence, "
        "what would disprove this, confidence, and one next check."
    )


def infer_model_capabilities(model_name: str, *, endpoint_is_local: bool = True) -> Dict[str, Any]:
    """Heuristic capability card from the model id (no network)."""
    name = str(model_name or "").strip().lower()
    cloud = (not endpoint_is_local) or any(
        k in name for k in (
            "gpt-", "gemini", "claude", "deepseek", "grok", "o1", "o3",
        )
    )
    small = bool(re.search(r"(^|[^\d])([1-3]b)\b", name)) or "mini" in name or "phi" in name
    large_local = bool(re.search(r"([7-9]b|\d{2,}b)\b", name))
    tool_calling = "yes" if (cloud or large_local) else ("partial" if small else "unknown")
    chaining = "yes" if (cloud or large_local) else "partial"
    long_ctx = "yes" if cloud else ("partial" if large_local else "partial")
    reasoning = "yes" if cloud else ("partial" if large_local else "partial")
    recommend = ""
    if small:
        recommend = "qwen2.5:7b (or larger) for Investigation"
    elif cloud:
        recommend = ""
    elif large_local:
        recommend = ""
    return {
        "ok": True,
        "model": str(model_name or "").strip(),
        "chat": "yes",
        "structured_output": "yes" if (cloud or large_local) else "partial",
        "tool_calling": tool_calling,
        "multi_tool_chaining": chaining,
        "long_context": long_ctx,
        "complex_reasoning": reasoning,
        "recommended": recommend,
        "source": "heuristic",
    }


def classify_trace_privacy(
    *,
    endpoint_is_local: bool = True,
    redact_task_names: bool = False,
    sensitive: bool = False,
) -> Dict[str, Any]:
    """Local / cloud-safe / sensitive classification for the current endpoint."""
    if sensitive:
        level = "sensitive"
        cloud_ok = False
        note = "Cloud AI disabled — treat this trace as confidential"
    elif endpoint_is_local:
        level = "local"
        cloud_ok = True
        note = "Raw trace and Findings stay on this machine"
    elif redact_task_names:
        level = "cloud_safe"
        cloud_ok = True
        note = "Task names anonymized; Findings still leave the machine"
    else:
        level = "cloud_safe"
        cloud_ok = True
        note = "Findings / metrics are sent to the configured cloud endpoint"
    return {
        "level": level,
        "cloud_ok": cloud_ok,
        "endpoint_is_local": bool(endpoint_is_local),
        "redact_task_names": bool(redact_task_names),
        "sensitive": bool(sensitive),
        "note": note,
    }


def anonymize_task_name(name: str, mapping: Optional[dict] = None) -> Tuple[str, Dict[str, str]]:
    """Stable Task-N alias. Returns (alias, updated mapping)."""
    src = str(name or "").strip()
    mp = dict(mapping or {})
    if not src:
        return src, mp
    if src in mp:
        return mp[src], mp
    alias = f"Task-{len(mp) + 1}"
    mp[src] = alias
    return alias, mp


def extract_task_names_from_text(text: str) -> List[str]:
    seen: List[str] = []
    for m in _TASK_NAME_RE.findall(str(text or "")):
        if m not in seen:
            seen.append(m)
    return seen


def anonymize_text(
    text: str,
    task_names: Optional[Sequence[str]] = None,
    mapping: Optional[dict] = None,
) -> Tuple[str, Dict[str, str]]:
    """Replace known task names with stable Task-N aliases."""
    src = str(text or "")
    mp = dict(mapping or {})
    names = [str(n).strip() for n in (task_names or []) if str(n).strip()]
    if not names:
        names = extract_task_names_from_text(src)
    names = sorted(set(names), key=len, reverse=True)
    out = src
    for name in names:
        alias, mp = anonymize_task_name(name, mp)
        if name and alias and name in out:
            out = out.replace(name, alias)
    return out, mp


def apply_cloud_privacy(
    findings_text: str = "",
    query: str = "",
    task_names: Optional[Sequence[str]] = None,
    *,
    endpoint_is_local: bool = True,
    redact_task_names: bool = False,
    sensitive: bool = False,
) -> Dict[str, Any]:
    """Block cloud send when sensitive; optionally anonymize task names."""
    priv = classify_trace_privacy(
        endpoint_is_local=endpoint_is_local,
        redact_task_names=redact_task_names,
        sensitive=sensitive,
    )
    blocked = bool(sensitive and not endpoint_is_local)
    text = str(findings_text or "")
    q = str(query or "")
    mapping: Dict[str, str] = {}
    if not endpoint_is_local and not blocked:
        text = sanitize_annotations_text(text)
        q = sanitize_annotations_text(q)
    if redact_task_names and not endpoint_is_local and not blocked:
        names = [str(n).strip() for n in (task_names or []) if str(n).strip()]
        if not names:
            names = extract_task_names_from_text(f"{text}\n{q}")
        text, mapping = anonymize_text(text, names, mapping)
        q, mapping = anonymize_text(q, names, mapping)
    return {
        "ok": not blocked,
        "blocked": blocked,
        "findings_text": text,
        "query": q,
        "mapping": mapping,
        "privacy": priv,
        "note": (
            "Cloud AI disabled — treat this trace as confidential"
            if blocked else priv.get("note") or ""
        ),
    }


def toggle_interpreted_scope(
    interpreted: Optional[dict] = None,
    key: str = "",
    enabled: Optional[bool] = None,
) -> Dict[str, Any]:
    """Flip one investigation-scope flag on an interpret_query payload."""
    out = dict(interpreted) if isinstance(interpreted, dict) else {}
    scopes = [str(s) for s in (out.get("scope") or []) if s]
    k = str(key or "").strip()
    if k:
        on = (k not in scopes) if enabled is None else bool(enabled)
        if on and k not in scopes:
            scopes.append(k)
        if not on:
            scopes = [s for s in scopes if s != k]
        out["scope"] = scopes
    return out


def interpreted_run_prompt(interpreted: Optional[dict] = None) -> str:
    """Prompt for [Run investigation] after the user confirms / edits scope."""
    data = interpreted if isinstance(interpreted, dict) else {}
    question = str(
        data.get("interpreted_question") or data.get("question") or ""
    ).strip() or "Investigate the main performance problem"
    mode = str(data.get("mode") or data.get("kind") or "diagnose")
    scopes = [str(s) for s in (data.get("scope") or []) if s]
    scope_bit = ", ".join(scopes) if scopes else "execution, blocking"
    fid = str(data.get("finding_id") or "").strip()
    extra = f" finding_id={fid}." if fid else ""
    return (
        f"{question}\n\nInterpreted as {mode}. "
        f"Investigation scope: {scope_bit}.{extra} "
        "Call interpret_query only if the question is still ambiguous, "
        "then investigate and verify jump:TIME evidence."
    )


def format_experiment_verdict(result: Any = None) -> str:
    raw = result
    if isinstance(result, dict):
        raw = result.get("result") or result.get("verdict") or ""
    key = str(raw or "").strip().upper()
    return {
        "VALIDATED": "Hypothesis validated",
        "DISPROVED": "Hypothesis disproved",
        "PARTIALLY VALIDATED": "Hypothesis partially validated",
    }.get(key, "Inconclusive")


def apply_experiment_to_hypotheses(
    hypotheses: Optional[Sequence[dict]] = None,
    result: Any = None,
) -> List[Dict[str, Any]]:
    """Mark open hypotheses supported / rejected from a validate_experiment result."""
    raw = result.get("result") if isinstance(result, dict) else result
    key = str(raw or "").strip().upper()
    status = (
        "supported" if key == "VALIDATED"
        else "rejected" if key == "DISPROVED"
        else ""
    )
    out: List[Dict[str, Any]] = []
    for h in hypotheses or []:
        if not isinstance(h, dict):
            continue
        item = dict(h)
        if status and str(item.get("status") or "").lower() in (
            "", "possible", "need_evidence", "needs_evidence", "untested",
        ):
            item["status"] = status
        out.append(item)
    return out


def parse_user_historical_knowledge(raw: Any) -> List[Dict[str, Any]]:
    if isinstance(raw, list):
        items = raw
    else:
        text = str(raw or "").strip()
        if not text:
            return []
        try:
            parsed = json.loads(text)
        except (TypeError, ValueError, json.JSONDecodeError):
            return []
        items = parsed if isinstance(parsed, list) else []
    out: List[Dict[str, Any]] = []
    for it in items:
        if not isinstance(it, dict):
            continue
        task = str(it.get("task") or "").strip()
        issue = str(it.get("issue") or it.get("previous_issue") or it.get("title") or "").strip()
        if not (task or issue):
            continue
        metrics = _metrics_from_mapping(it.get("metrics") if isinstance(it.get("metrics"), dict) else it)
        out.append({
            "task": task,
            "issue": issue,
            "fix": str(it.get("fix") or it.get("known_fix") or "").strip(),
            "build": str(it.get("build") or it.get("last_occurrence") or "").strip(),
            "keywords": list(it.get("keywords") or []),
            "metrics": metrics,
        })
    return out


def dump_user_historical_knowledge(items: Optional[Sequence[dict]] = None) -> str:
    return json.dumps(parse_user_historical_knowledge(list(items or [])), ensure_ascii=False)


def new_user_historical_entry(
    finding: Optional[dict] = None,
    extras: Optional[dict] = None,
) -> Dict[str, Any]:
    f = finding if isinstance(finding, dict) else {}
    extra = extras if isinstance(extras, dict) else {}
    task = str(extra.get("task") or f.get("task") or "").strip()
    issue = str(
        extra.get("issue") or extra.get("title") or f.get("title") or ""
    ).strip() or "Saved finding"
    metrics = _metrics_from_mapping(extra.get("metrics") if isinstance(extra.get("metrics"), dict) else extra)
    if not metrics:
        metrics = _metrics_from_mapping(f)
    return {
        "task": task,
        "issue": issue,
        "fix": str(extra.get("fix") or "").strip(),
        "build": str(extra.get("build") or "").strip(),
        "keywords": [w for w in re.split(r"\W+", issue.lower()) if len(w) > 3][:6],
        "metrics": metrics,
    }


_HISTORICAL_METRIC_KEYS: Tuple[str, ...] = (
    "migrations", "migration_rate", "blocking", "wcet",
)


def _metrics_from_mapping(src: Any) -> Dict[str, float]:
    data = src if isinstance(src, dict) else {}
    out: Dict[str, float] = {}
    for key in _HISTORICAL_METRIC_KEYS:
        try:
            if data.get(key) is None:
                continue
            out[key] = float(data.get(key))
        except (TypeError, ValueError):
            continue
    return out


def rate_flags_from_metrics(
    current: Optional[dict] = None,
    typical: Optional[dict] = None,
) -> List[str]:
    """Typical vs current rate lines (e.g. migrations 47 vs typical 12)."""
    cur = _metrics_from_mapping(current)
    hist = _metrics_from_mapping(typical)
    flags: List[str] = []
    for key in _HISTORICAL_METRIC_KEYS:
        if key not in cur or key not in hist or hist[key] == 0:
            continue
        ratio = cur[key] / hist[key]
        if ratio >= 2.0:
            flags.append(f"{key} {cur[key]:g} vs typical {hist[key]:g} (×{ratio:.1f})")
    return flags


CAPABILITY_CHAT_PROBE = 'Reply with JSON only: {"ok":true}'

CAPABILITY_PROBE_TOOL: Dict[str, Any] = {
    "type": "function",
    "function": {
        "name": "btf_ping",
        "description": "Capability probe. Call this once if you support tools.",
        "parameters": {"type": "object", "properties": {}},
    },
}

CAPABILITY_PROBE_TOOL_PONG: Dict[str, Any] = {
    "type": "function",
    "function": {
        "name": "btf_pong",
        "description": "Second capability probe. Call after btf_ping if you can chain tools.",
        "parameters": {"type": "object", "properties": {}},
    },
}


def capability_probe_body(model: str) -> Dict[str, Any]:
    return {
        "model": str(model or "").strip(),
        "stream": False,
        "messages": [{
            "role": "user",
            "content": (
                "If you can call tools, call btf_ping then btf_pong. "
                "Otherwise reply PONG."
            ),
        }],
        "tools": [CAPABILITY_PROBE_TOOL, CAPABILITY_PROBE_TOOL_PONG],
        "max_tokens": 64,
    }


def structured_output_from_text(text: str) -> bool:
    src = str(text or "").strip()
    if src.startswith("```"):
        src = re.sub(r"^```(?:json)?\s*", "", src, flags=re.IGNORECASE)
        src = re.sub(r"\s*```$", "", src)
    try:
        return isinstance(json.loads(src), dict)
    except (TypeError, ValueError, json.JSONDecodeError):
        m = re.search(r"\{[^{}]+\}", src)
        if not m:
            return False
        try:
            return isinstance(json.loads(m.group(0)), dict)
        except (TypeError, ValueError, json.JSONDecodeError):
            return False


def count_tool_calls(body: Any) -> Optional[int]:
    if not isinstance(body, dict):
        return None
    choices = body.get("choices")
    if not isinstance(choices, list) or not choices:
        return None
    msg = choices[0].get("message") if isinstance(choices[0], dict) else None
    if not isinstance(msg, dict):
        return None
    calls = msg.get("tool_calls")
    n = len(calls) if isinstance(calls, list) else 0
    if msg.get("function_call"):
        n = max(n, 1)
    if n:
        return n
    if str(msg.get("content") or "").strip():
        return 0
    return None


def merge_live_capability(
    cap: Optional[dict] = None,
    *,
    chat_text: str = "",
    tool_body: Any = None,
    tool_ok: Optional[bool] = None,
) -> Dict[str, Any]:
    """Overlay live Test-connection results on the heuristic capability card."""
    out = dict(cap) if isinstance(cap, dict) else {}
    if structured_output_from_text(chat_text):
        out["structured_output"] = "yes"
        out["source"] = "live"
    elif str(chat_text or "").strip():
        out["structured_output"] = "no"
        out["source"] = "live"
    n = count_tool_calls(tool_body) if tool_body is not None else None
    if tool_ok is True or (n is not None and n >= 1):
        out["tool_calling"] = "yes"
        out["multi_tool_chaining"] = "yes" if (n or 0) >= 2 else "partial"
        out["source"] = "live"
    elif tool_ok is False or n == 0:
        out["tool_calling"] = "no"
        out["multi_tool_chaining"] = "no"
        out["source"] = "live"
    return out


def tool_calling_from_chat_response(body: Any) -> Optional[bool]:
    """True if the chat response issued a tool call; False if text-only; None if empty."""
    if not isinstance(body, dict):
        return None
    choices = body.get("choices")
    if not isinstance(choices, list) or not choices:
        return None
    msg = choices[0].get("message") if isinstance(choices[0], dict) else None
    if not isinstance(msg, dict):
        return None
    calls = msg.get("tool_calls") or msg.get("function_call")
    if calls:
        return True
    if str(msg.get("content") or "").strip():
        return False
    return None


def builtin_investigation_templates() -> List[Dict[str, Any]]:
    """Reusable tool sequences teams can run as 'My Investigation'."""
    return [
        {
            "id": "cpu_latency",
            "label": "CPU Latency Investigation",
            "steps": [
                "detect_anomalies",
                "investigate",
                "query_raw_metric",
                "correlate_events",
                "find_critical_path",
                "detect_priority_inversion",
                "generate_report",
            ],
        },
        {
            "id": "migration_thrash",
            "label": "Migration Thrash Investigation",
            "steps": [
                "detect_anomalies",
                "investigate",
                "correlate_events",
                "query_raw_metric",
                "what_if",
            ],
        },
        {
            "id": "regression",
            "label": "A/B Regression Investigation",
            "steps": [
                "compare_performance",
                "regression_explain",
                "validate_experiment",
                "generate_report",
            ],
        },
    ]


def match_historical_knowledge(
    task: str,
    *,
    current: Optional[dict] = None,
    history: Optional[dict] = None,
) -> Dict[str, Any]:
    """Compare a task's current metrics with a stored baseline profile."""
    name = str(task or "").strip()
    cur = current if isinstance(current, dict) else {}
    hist = history if isinstance(history, dict) else {}
    prev = hist.get(name) if isinstance(hist.get(name), dict) else (
        hist.get("tasks", {}).get(name) if isinstance(hist.get("tasks"), dict) else {}
    )
    if not isinstance(prev, dict):
        prev = {}
    flags = rate_flags_from_metrics(cur, prev)
    issue = str(prev.get("issue") or prev.get("previous_issue") or "")
    fix = str(prev.get("fix") or prev.get("known_fix") or "")
    build = str(prev.get("build") or prev.get("last_occurrence") or "")
    resembles = bool(issue) and bool(flags)
    return {
        "ok": True,
        "task": name,
        "previous_issue": issue,
        "known_fix": fix,
        "last_occurrence": build,
        "flags": flags,
        "typical": _metrics_from_mapping(prev),
        "current": _metrics_from_mapping(cur),
        "resembles_previous": resembles,
        "message": (
            f"This resembles the {issue} issue"
            + (f" seen in {build}" if build else "")
            if resembles else
            ("No historical match" if not prev else "Within historical range")
        ),
    }


def builtin_historical_catalog() -> List[Dict[str, Any]]:
    """Keyword catalog for common firmware investigation classes."""
    return [
        {
            "keywords": ("thrash", "migration", "bounc"),
            "issue": "Migration thrashing",
            "fix": "Pin the task / set core affinity",
            "build": "typical",
        },
        {
            "keywords": ("mutex", "contention", "blocking"),
            "issue": "Mutex contention",
            "fix": "Shorten the critical section or enable priority inheritance",
            "build": "typical",
        },
        {
            "keywords": ("inversion", "inherit"),
            "issue": "Priority inversion",
            "fix": "Priority inheritance or priority ceiling on the mutex",
            "build": "typical",
        },
        {
            "keywords": ("imbalance", "load balance"),
            "issue": "Load imbalance",
            "fix": "Rebalance placement or pin heavy tasks",
            "build": "typical",
        },
        {
            "keywords": ("deadline", "budget"),
            "issue": "Deadline miss",
            "fix": "Trim WCET or raise the budget / period",
            "build": "typical",
        },
    ]


def historical_knowledge_for_finding(
    finding: Optional[dict] = None,
    *,
    history: Optional[dict] = None,
    current: Optional[dict] = None,
    user_catalog: Optional[Sequence[dict]] = None,
) -> Dict[str, Any]:
    """Match user store, then baseline history, then the builtin catalog."""
    finding = finding if isinstance(finding, dict) else {}
    task = str(finding.get("task") or "")
    cur = current if isinstance(current, dict) else {}
    blob = f"{finding.get('title') or ''} {finding.get('text') or ''} {task}".lower()
    for item in parse_user_historical_knowledge(list(user_catalog or [])):
        item_task = str(item.get("task") or "").strip()
        keys = [str(k).lower() for k in (item.get("keywords") or []) if k]
        if (item_task and item_task.lower() == task.lower()) or (
            keys and any(k in blob for k in keys)
        ) or (item.get("issue") and str(item.get("issue")).lower() in blob):
            issue = str(item.get("issue") or "")
            fix = str(item.get("fix") or "")
            build = str(item.get("build") or "")
            typical = item.get("metrics") if isinstance(item.get("metrics"), dict) else {}
            flags = rate_flags_from_metrics(cur, typical)
            return {
                "ok": True,
                "task": task or item_task,
                "previous_issue": issue,
                "known_fix": fix,
                "last_occurrence": build,
                "flags": flags,
                "typical": typical,
                "current": _metrics_from_mapping(cur),
                "resembles_previous": True,
                "source": "user",
                "message": f"This resembles the {issue} issue"
                + (f" seen in {build}" if build else "")
                + (f" — known fix: {fix}" if fix else ""),
            }
    hit = match_historical_knowledge(task, current=cur, history=history)
    if hit.get("previous_issue") or hit.get("flags"):
        return hit
    for item in builtin_historical_catalog():
        if any(k in blob for k in (item.get("keywords") or ())):
            issue = str(item.get("issue") or "")
            fix = str(item.get("fix") or "")
            build = str(item.get("build") or "")
            return {
                "ok": True,
                "task": task,
                "previous_issue": issue,
                "known_fix": fix,
                "last_occurrence": build,
                "flags": [],
                "resembles_previous": True,
                "source": "catalog",
                "message": f"This resembles the {issue} issue"
                + (f" — known fix: {fix}" if fix else ""),
            }
    return hit


def build_investigation_case(
    investigate_ctx: Optional[dict] = None,
    *,
    question: str = "",
    trace: str = "",
    cursor_lo: Optional[float] = None,
    cursor_hi: Optional[float] = None,
    tools_run: Optional[Sequence[str]] = None,
    tools_executed: Optional[Sequence[str]] = None,
    mode: str = "diagnose",
    score_data: Optional[dict] = None,
    finding: Optional[dict] = None,
    hypotheses: Optional[Sequence[dict]] = None,
    alternatives: Optional[Sequence[dict]] = None,
    evidence: Optional[Sequence[dict]] = None,
    conclusion: str = "",
    confidence: str = "",
    checks: Optional[Sequence[dict]] = None,
    plan: Optional[dict] = None,
    **_extra: Any,
) -> Dict[str, Any]:
    """Assemble a Case from an ``investigate`` context (and optional extras)."""
    ctx = dict(investigate_ctx) if isinstance(investigate_ctx, dict) else {}
    if finding is not None:
        ctx["finding"] = finding
    if hypotheses is not None:
        ctx["hypotheses"] = list(hypotheses)
    if alternatives is not None:
        ctx["alternatives"] = list(alternatives)
    if evidence is not None:
        ctx["evidence"] = list(evidence)
    if checks is not None:
        ctx["checks"] = list(checks)
    if plan is not None:
        ctx["plan"] = plan
    if conclusion:
        ctx.setdefault("conclusion", conclusion)
    if score_data is None and isinstance(ctx.get("score_data"), dict):
        score_data = ctx.get("score_data")
    if score_data is None and isinstance(ctx.get("scoreData"), dict):
        score_data = ctx.get("scoreData")
    run = tools_run or tools_executed or ctx.get("tools_executed")
    finding_obj = ctx.get("finding") if isinstance(ctx.get("finding"), dict) else {}
    ev = list(
        evidence
        or finding_obj.get("evidence")
        or ctx.get("evidence")
        or []
    )
    hyps = enrich_hypotheses(
        ctx.get("hypotheses") or [],
        evidence=ev,
        alternatives=ctx.get("alternatives") or [],
    )
    graph = build_evidence_graph(
        finding_obj or None,
        evidence=ev,
        hypotheses=hyps,
        chain=ctx.get("root_cause_chain") or [],
    )
    score = score_data if isinstance(score_data, dict) else {}
    quality = compute_evidence_quality(
        score=score.get("score", ctx.get("evidence_score", 0)),
        breakdown=score.get("breakdown") or ctx.get("evidence_score_breakdown"),
        evidence=ev,
        alternatives=ctx.get("alternatives") or [],
        checks=ctx.get("checks") or [],
        evidence_chain=str(ctx.get("evidence_chain") or ""),
    )
    coverage = compute_evidence_coverage(evidence=ev)
    falsify = falsification_checks(finding_obj or None)
    if ev:
        falsify["supporting"] = [
            str(e.get("label") or "evidence")
            + (f" jump:{e.get('time')}" if e.get("time") is not None else "")
            for e in ev[:8] if isinstance(e, dict)
        ]
    tool_names: List[str] = []
    for t in (run or []):
        if isinstance(t, dict):
            n = str(t.get("name") or "").strip()
        else:
            n = str(t or "").strip()
        if n:
            tool_names.append(n)
    reasons = [
        {"tool": n, "reason": tool_call_reason(n, finding_obj or None)}
        for n in tool_names
    ]
    case = empty_investigation_case(
        question=question or str(ctx.get("message") or ctx.get("question") or ""),
        trace=trace,
        cursor_lo=cursor_lo,
        cursor_hi=cursor_hi,
        tasks=[str(finding_obj.get("task") or "")] if finding_obj.get("task") else [],
    )
    case.update({
        "suspected_findings": [finding_obj] if finding_obj else list(ctx.get("related_findings") or []),
        "hypotheses": hyps,
        "evidence": ev,
        "tools_executed": tool_names,
        "tool_reasons": reasons,
        "evidence_timeline": [
            {"time": e.get("time"), "label": e.get("label")}
            for e in ev if isinstance(e, dict) and e.get("time") is not None
        ],
        "evidence_graph": graph,
        "evidence_quality": quality,
        "evidence_coverage": coverage,
        "coverage": coverage,
        "falsification": falsify,
        "falsify": falsify,
        "graph_mermaid": graph.get("mermaid") or "",
        "confidence": confidence or quality.get("confidence_label") or "Medium",
        "confidence_history": record_confidence_step(
            [], tool_name="investigate",
            score=quality.get("score"), band=quality.get("band"),
            note="Initial investigation context",
        ),
        "conclusion": conclusion or str(finding_obj.get("title") or ""),
        "alternatives_rejected": [
            a for a in (ctx.get("alternatives") or [])
            if isinstance(a, dict) and str(a.get("status") or "").lower() == "rejected"
        ],
        "recommended_action": str(falsify.get("next_check") or ""),
        "mode": mode if mode in INVESTIGATION_MODES else "diagnose",
        "plan": ctx.get("plan"),
    })
    return case


def update_case_from_tool(
    case: Optional[dict],
    tool_name: str,
    result: Optional[dict] = None,
) -> Dict[str, Any]:
    """Fold a tool result into an existing Case (confidence evolution)."""
    out = dict(case or empty_investigation_case())
    name = str(tool_name or "").strip()
    tools = list(out.get("tools_executed") or [])
    if name and name not in tools:
        tools.append(name)
    out["tools_executed"] = tools
    reasons = list(out.get("tool_reasons") or [])
    finding = None
    suspected = out.get("suspected_findings") or []
    if suspected and isinstance(suspected[0], dict):
        finding = suspected[0]
    reasons.append({"tool": name, "reason": tool_call_reason(name, finding)})
    out["tool_reasons"] = reasons
    data = {}
    if isinstance(result, dict):
        data = result.get("data") if isinstance(result.get("data"), dict) else result
    ev = list(out.get("evidence") or [])
    for key in ("evidence", "events", "path"):
        for item in data.get(key) or []:
            if isinstance(item, dict):
                ev.append({
                    "label": str(item.get("label") or item.get("detail") or item.get("kind") or "evidence"),
                    "time": item.get("time"),
                })
    out["evidence"] = ev
    score = None
    if isinstance(data.get("evidence_score"), (int, float)):
        score = data.get("evidence_score")
    hist = record_confidence_step(
        out.get("confidence_history"),
        tool_name=name,
        score=score,
        note=str((result or {}).get("message") or "")[:160],
    )
    out["confidence_history"] = hist
    return out


# ---------------------------------------------------------------------------
# Benchmark / regression helpers (offline; no live model required)
# ---------------------------------------------------------------------------

BENCHMARK_METRIC_WEIGHTS: Dict[str, float] = {
    "finding": 0.20,
    "evidence": 0.20,
    "tool_use": 0.15,
    "root_cause": 0.20,
    "calibration": 0.10,
    "safety": 0.15,
}


def score_benchmark_case(
    expected: dict,
    *,
    actual_finding_ids: Optional[Sequence[str]] = None,
    actual_tasks: Optional[Sequence[str]] = None,
    actual_tools: Optional[Sequence[str]] = None,
    actual_conclusion: str = "",
    validation: Optional[dict] = None,
    evidence_quality: Optional[dict] = None,
) -> Dict[str, Any]:
    """Weighted diagnostic score for one expected-facts case (0–100)."""
    exp = expected if isinstance(expected, dict) else {}
    want_findings = [str(x).lower() for x in (exp.get("finding_types") or [])]
    got_findings = [str(x).lower() for x in (actual_finding_ids or [])]
    finding_hits = sum(1 for w in want_findings if any(w in g for g in got_findings))
    finding_score = 100 if not want_findings else int(
        round(100.0 * finding_hits / len(want_findings)))

    want_tasks = [str(x).lower() for x in (exp.get("tasks") or [])]
    got_tasks = [str(x).lower() for x in (actual_tasks or [])]
    task_hits = sum(1 for w in want_tasks if any(w in g for g in got_tasks))
    evidence_score = 100 if not want_tasks else int(
        round(100.0 * task_hits / len(want_tasks)))
    ev = exp.get("evidence") if isinstance(exp.get("evidence"), dict) else {}
    want_metrics = [str(x).lower() for x in (ev.get("required_metrics") or [])]
    if want_metrics:
        blob = str(actual_conclusion or "").lower()
        metric_hits = sum(1 for m in want_metrics if m in blob)
        metric_score = int(round(100.0 * metric_hits / len(want_metrics)))
        evidence_score = (
            metric_score if not want_tasks
            else int(round((evidence_score + metric_score) / 2.0))
        )

    allowed = [str(x) for x in (exp.get("allowed_tools") or [])]
    got_tools = [str(x) for x in (actual_tools or [])]
    if allowed:
        tool_hits = sum(1 for t in got_tools if t in allowed)
        tool_score = int(round(100.0 * tool_hits / max(len(allowed), 1)))
        if got_tools and tool_hits == 0:
            tool_score = 0
        elif got_tools:
            tool_score = max(tool_score, int(round(100.0 * tool_hits / len(got_tools))))
    else:
        tool_score = 100 if got_tools else 50

    want_class = str(exp.get("root_cause_class") or "").lower()
    conc = str(actual_conclusion or "").lower()
    if not want_class:
        root_score = 100
    elif want_class in conc or any(w in conc for w in want_class.split()):
        root_score = 100
    else:
        root_score = 0

    band = str((evidence_quality or {}).get("band") or "")
    cal = 80
    if band in ("strong", "medium-high"):
        cal = 90
    elif band == "medium":
        cal = 75
    elif band in ("weak", "insufficient"):
        cal = 55

    val = validation if isinstance(validation, dict) else {}
    safety = 100 if val.get("ok", True) else max(
        0, 100 - 20 * int(val.get("unverified") or 1))
    if exp.get("forbidden", {}).get("invented_task_names") and any(
        c.get("kind") == "task" and not c.get("ok")
        for c in (val.get("claims") or [])
        if isinstance(c, dict)
    ):
        safety = min(safety, 40)

    parts = {
        "finding": finding_score,
        "evidence": evidence_score,
        "tool_use": tool_score,
        "root_cause": root_score,
        "calibration": cal,
        "safety": safety,
    }
    overall = int(round(sum(
        parts[k] * BENCHMARK_METRIC_WEIGHTS[k] for k in parts
    )))
    return {
        "overall": max(0, min(100, overall)),
        "parts": parts,
    }


def format_benchmark_score(score: dict) -> str:
    overall = _safe_int((score or {}).get("overall"))
    filled = max(0, min(10, int(round(overall / 10))))
    bar = "█" * filled + "░" * (10 - filled)
    parts = (score or {}).get("parts") or {}
    lines = [f"Overall AI Diagnostic Score", f"{bar} {overall}", ""]
    for key in ("finding", "evidence", "tool_use", "root_cause", "calibration", "safety"):
        if key in parts:
            label = {
                "finding": "Finding",
                "evidence": "Evidence",
                "tool_use": "Tool use",
                "root_cause": "Root cause",
                "calibration": "Calibration",
                "safety": "Safety / grounding",
            }[key]
            lines.append(f"{label:20} {parts[key]}")
    return "\n".join(lines)


def _cases_from_json_obj(raw: Any) -> List[Dict[str, Any]]:
    if isinstance(raw, list):
        return [c for c in raw if isinstance(c, dict)]
    if isinstance(raw, dict) and isinstance(raw.get("cases"), list):
        return [c for c in raw["cases"] if isinstance(c, dict)]
    if isinstance(raw, dict) and raw.get("id"):
        return [raw]
    raise ValueError("benchmark dataset must be a JSON list, {cases: [...]}, or a case object")


def load_benchmark_dataset(path: str) -> List[Dict[str, Any]]:
    """Load ``tests/ai/dataset.json`` or a directory of JSON cases + traces."""
    src = Path(path)
    if src.is_dir():
        index = src / "dataset.json"
        if index.is_file():
            files = [index]
        else:
            files = sorted(
                p for p in src.glob("*.json")
                if p.name != "package.json"
            )
        if not files:
            raise FileNotFoundError(f"no dataset.json or *.json cases in {src}")
        cases: List[Dict[str, Any]] = []
        for f in files:
            with f.open("r", encoding="utf-8") as fh:
                cases.extend(_cases_from_json_obj(json.load(fh)))
        root = src
    elif src.is_file():
        with src.open("r", encoding="utf-8") as fh:
            cases = _cases_from_json_obj(json.load(fh))
        root = src.parent
    else:
        raise FileNotFoundError(f"benchmark dataset not found: {src}")
    seen: set = set()
    out: List[Dict[str, Any]] = []
    for case in cases:
        cid = str(case.get("id") or "")
        if cid and cid in seen:
            continue
        if cid:
            seen.add(cid)
        trace = str(case.get("trace") or "").strip()
        if trace:
            tp = Path(trace)
            case = dict(case)
            case["trace_path"] = str(tp if tp.is_absolute() else (root / tp).resolve())
        baseline = str(case.get("baseline_trace") or case.get("baseline") or "").strip()
        if baseline:
            bp = Path(baseline)
            case = dict(case)
            case["baseline_path"] = str(bp if bp.is_absolute() else (root / bp).resolve())
        out.append(case)
    return out


def evidence_quality_from_score(
    score: Any,
    breakdown: Optional[Sequence[dict]] = None,
    **kwargs: Any,
) -> Dict[str, Any]:
    """Alias used by the Evidence panel (same as ``compute_evidence_quality``)."""
    return compute_evidence_quality(
        score=score, breakdown=breakdown, **kwargs,
    )


def build_validation_catalog(
    *,
    findings_text: str = "",
    evidence: Optional[Sequence[dict]] = None,
    tasks: Optional[Sequence[str]] = None,
    metrics: Optional[Sequence[str]] = None,
    cursor_lo: Optional[float] = None,
    cursor_hi: Optional[float] = None,
    tool_times: Optional[Sequence[Any]] = None,
) -> Dict[str, Any]:
    """Known tasks / times / cursor window for ``validate_ai_response``."""
    known_tasks = [str(t) for t in (tasks or []) if t]
    for tok in _TASK_NAME_RE.findall(str(findings_text or "")):
        if tok not in known_tasks:
            known_tasks.append(tok)
    times: List[float] = []
    for e in evidence or []:
        if isinstance(e, dict) and e.get("time") is not None:
            try:
                times.append(float(e.get("time")))
            except (TypeError, ValueError):
                pass
    for t in tool_times or []:
        try:
            times.append(float(t))
        except (TypeError, ValueError):
            pass
    lo = cursor_lo
    hi = cursor_hi
    try:
        lo = float(lo) if lo is not None else None
    except (TypeError, ValueError):
        lo = None
    try:
        hi = float(hi) if hi is not None else None
    except (TypeError, ValueError):
        hi = None
    return {
        "tasks": known_tasks,
        "metrics": sorted(str(m) for m in (metrics or _KNOWN_METRICS)),
        "times": times,
        "cursor_lo": lo,
        "cursor_hi": hi,
    }


def infer_model_capability(
    model_name: str,
    *,
    tool_call_ok: Optional[bool] = None,
    chat_ok: bool = True,
    endpoint_is_local: bool = True,
    chat_text: str = "",
    tool_body: Any = None,
) -> Dict[str, Any]:
    cap = infer_model_capabilities(
        model_name, endpoint_is_local=endpoint_is_local,
    )
    cap["chat"] = "yes" if chat_ok else "no"
    if tool_call_ok is True:
        cap["tool_calling"] = "yes"
    elif tool_call_ok is False:
        cap["tool_calling"] = "partial"
    return merge_live_capability(
        cap, chat_text=chat_text, tool_body=tool_body, tool_ok=tool_call_ok,
    )


def format_capability_report(cap: Optional[Dict[str, Any]] = None) -> str:
    if not isinstance(cap, dict):
        return ""
    glyph = {"yes": "✓", "partial": "△", "no": "✗", "unknown": "?"}
    def g(v: Any) -> str:
        return glyph.get(str(v), str(v or ""))
    lines = [
        "Model capability",
        "",
        f"{g(cap.get('chat'))} Chat",
        f"{g(cap.get('structured_output'))} Structured output",
        f"{g(cap.get('tool_calling'))} Tool calling",
        f"{g(cap.get('multi_tool_chaining'))} Multi-tool chaining",
        f"{g(cap.get('long_context'))} Long context",
        f"{g(cap.get('complex_reasoning'))} Complex reasoning",
    ]
    rec = str(cap.get("recommended") or "").strip()
    if rec:
        lines.extend(["", f"Recommended: {rec}"])
    return "\n".join(lines)


def format_benchmark_report(run_id: str, rows: Sequence[Dict[str, Any]]) -> str:
    lines = [f"AI Benchmark #{run_id}", "", f"Cases: {len(rows)}", ""]
    for row in rows:
        name = str(row.get("id") or "?")
        score = row.get("overall")
        flag = "PASS" if row.get("pass") else "FAIL"
        lines.append(f"  {name:24} {score!s:>3}  {flag}")
    if rows:
        avg = int(round(sum(int(r.get("overall") or 0) for r in rows) / len(rows)))
        lines.extend(["", f"Overall {avg}"])
    return "\n".join(lines) + "\n"


def _xml_text(el: Any) -> str:
    return (el.text or "").strip() if el is not None else ""


def _xml_child(parent: Any, *names: str) -> Any:
    if parent is None:
        return None
    for name in names:
        found = parent.find(name)
        if found is not None:
            return found
    return None


def resolve_benchmark_api_key(*, text: str = "", env: str = "") -> str:
    """Named env, else XML text, else shared env fallbacks."""
    from .ai_assistant import normalize_api_key, read_ai_env_key, resolve_ai_api_key

    env_name = str(env or "").strip()
    if env_name:
        got = read_ai_env_key((env_name,))
        if got:
            return got
    got = normalize_api_key(text)
    if got:
        return got
    return resolve_ai_api_key("")


def _parse_benchmark_endpoint_xml(el: Any, defaults: Optional[dict] = None) -> Dict[str, Any]:
    from .ai_assistant import (
        normalize_ai_base_url,
        parse_ai_tls_verify,
    )

    out = dict(defaults or {})
    if not out.get("base_url"):
        out["base_url"] = ""
    if "tls_verify" not in out:
        out["tls_verify"] = True
    if "api_key" not in out:
        out["api_key"] = ""
    if "api_key_env" not in out:
        out["api_key_env"] = ""
    if "preset" not in out:
        out["preset"] = ""
    if "timeout_s" not in out:
        out["timeout_s"] = 0.0
    if el is None:
        return out
    url_el = _xml_child(el, "base-url", "base_url", "url")
    url = _xml_text(url_el) or str(el.get("base-url") or el.get("base_url") or "").strip()
    if url:
        out["base_url"] = normalize_ai_base_url(url)
    tls_raw = None
    tls_el = _xml_child(el, "tls-verify", "tls_verify")
    if tls_el is not None:
        tls_raw = _xml_text(tls_el) or tls_el.get("value")
    if el.get("tls-verify") is not None:
        tls_raw = el.get("tls-verify")
    elif el.get("tls_verify") is not None:
        tls_raw = el.get("tls_verify")
    if tls_raw is not None:
        out["tls_verify"] = parse_ai_tls_verify(tls_raw, default=True)
    if str(el.get("insecure") or "").strip().lower() in (
        "1", "true", "yes", "on",
    ):
        out["tls_verify"] = False
    key_el = _xml_child(el, "api-key", "api_key")
    env_name = ""
    key_text = ""
    if key_el is not None:
        env_name = str(key_el.get("env") or "").strip()
        key_text = _xml_text(key_el)
    env_name = env_name or str(el.get("api-key-env") or el.get("api_key_env") or "").strip()
    if env_name or key_text:
        out["api_key_env"] = env_name
        out["api_key"] = resolve_benchmark_api_key(text=key_text, env=env_name)
    preset_el = _xml_child(el, "preset")
    preset = _xml_text(preset_el) or str(el.get("preset") or "").strip()
    if preset:
        out["preset"] = preset
    to_el = _xml_child(el, "timeout-s", "timeout_s", "timeout")
    to_raw = _xml_text(to_el) or str(el.get("timeout-s") or el.get("timeout_s") or "").strip()
    if to_raw:
        try:
            out["timeout_s"] = float(to_raw)
        except ValueError:
            pass
    return out


def load_benchmark_suite_xml(path: Any) -> Dict[str, Any]:
    """Load a live ``ai-test`` suite from XML (models, URL, TLS, API key)."""
    import xml.etree.ElementTree as ET

    src = Path(path)
    if not src.is_file():
        raise FileNotFoundError(f"benchmark suite not found: {src}")
    try:
        root = ET.parse(str(src)).getroot()
    except ET.ParseError as exc:
        raise ValueError(f"invalid benchmark XML {src}: {exc}") from exc
    tag = str(root.tag or "").rsplit("}", 1)[-1].lower()
    if tag not in ("ai-benchmark", "benchmark", "suite"):
        raise ValueError(
            f"benchmark XML root must be <ai-benchmark> (got <{root.tag}>)"
        )
    xml_dir = src.parent
    cwd = Path.cwd()

    def _resolve(value: str) -> str:
        raw = str(value or "").strip()
        if not raw:
            return ""
        p = Path(raw)
        if p.is_absolute():
            return str(p)
        for base in (cwd, xml_dir):
            cand = (base / raw).resolve()
            if cand.exists():
                return str(cand)
        return str((cwd / raw).resolve())

    dataset_el = _xml_child(root, "dataset")
    output_el = _xml_child(root, "output")
    fail_el = _xml_child(root, "fail-under", "fail_under")
    fail_under = 0
    fail_raw = _xml_text(fail_el)
    if fail_raw:
        try:
            fail_under = int(fail_raw)
        except ValueError:
            fail_under = 0
    defaults = _parse_benchmark_endpoint_xml(_xml_child(root, "endpoint", "defaults"))
    models_el = _xml_child(root, "models")
    model_nodes = list((models_el if models_el is not None else root).findall("model"))
    models: List[Dict[str, Any]] = []
    for node in model_nodes:
        mid = str(node.get("id") or node.get("name") or _xml_text(node) or "").strip()
        if not mid:
            continue
        ep = _parse_benchmark_endpoint_xml(node, defaults)
        if not ep.get("base_url"):
            raise ValueError(f"model {mid!r} has no base-url (set <endpoint> or per-model)")
        models.append({
            "id": mid,
            "base_url": ep["base_url"],
            "tls_verify": bool(ep.get("tls_verify", True)),
            "api_key": str(ep.get("api_key") or ""),
            "api_key_env": str(ep.get("api_key_env") or ""),
            "preset": str(ep.get("preset") or ""),
            "timeout_s": float(ep.get("timeout_s") or 0.0),
        })
    if not models:
        raise ValueError("benchmark XML has no <model id=...> entries")
    dataset = _xml_text(dataset_el) or "tests/ai"
    return {
        "path": str(src.resolve()),
        "dataset": _resolve(dataset),
        "dataset_raw": dataset,
        "fail_under": fail_under,
        "output": _xml_text(output_el),
        "defaults": defaults,
        "models": models,
    }


def parse_live_benchmark_models(models_raw: str) -> List[str]:
    """Comma-separated model ids from ``--models`` (filters the suite XML)."""
    return [m.strip() for m in str(models_raw or "").split(",") if m.strip()]


def select_benchmark_suite_models(
    suite: dict,
    models_raw: str = "",
) -> List[Dict[str, Any]]:
    """Return suite model dicts, optionally filtered by ``--models`` ids."""
    models = list((suite or {}).get("models") or [])
    want = parse_live_benchmark_models(models_raw)
    if not want:
        return models
    by_id = {str(m.get("id") or ""): m for m in models}
    out: List[Dict[str, Any]] = []
    missing: List[str] = []
    for mid in want:
        if mid in by_id:
            out.append(by_id[mid])
        else:
            missing.append(mid)
    if missing:
        known = ", ".join(by_id) or "(none)"
        raise ValueError(
            f"model id(s) not in suite XML: {', '.join(missing)} (have {known})"
        )
    return out


def benchmark_model_category(model: str) -> str:
    low = str(model or "").lower()
    if "gemini" in low:
        if "flash-lite" in low or "flash_lite" in low:
            return "Cloud / fast"
        if "pro" in low:
            return "Cloud / frontier"
        return "Cloud"
    if "gpt-" in low or "gpt4" in low:
        return "Cloud"
    if "phi4" in low or "phi-4" in low:
        return "Local / historical baseline"
    if "35b" in low or "a3b" in low:
        return "Local / experimental"
    if any(tok in low for tok in ("27b", "26b", "14b", "32b")):
        return "Local / high-quality"
    return "Local / practical"


def benchmark_prompt_context(case: dict) -> str:
    """Catalog-only Findings text for a live case (does not leak expected labels)."""
    catalog = case.get("catalog") if isinstance(case.get("catalog"), dict) else {}
    tasks = ", ".join(str(t) for t in (catalog.get("tasks") or []) if str(t).strip())
    times = catalog.get("times") or []
    jumps = ", ".join(f"jump:{t}" for t in times)
    lo, hi = catalog.get("cursor_lo"), catalog.get("cursor_hi")
    lines = [
        "Benchmark investigation. Use only this catalog.",
        f"Trace: {case.get('trace') or ''}",
        f"Known tasks: {tasks or '(none)'}",
    ]
    if lo is not None and hi is not None:
        lines.append(f"Cursor region window: jump:{lo} … jump:{hi}")
    if jumps:
        lines.append(f"Evidence times: {jumps}")
    lines.append(
        "Call an allowed investigation tool if needed. "
        "Cite jump:TIME and Task[id] from the catalog. "
        "State confidence (High / Medium / Low). "
        "Do not invent tasks, metrics, or timestamps."
    )
    return "\n".join(lines)


def score_benchmark_response(
    case: dict,
    *,
    response: str,
    tools: Optional[Sequence[str]] = None,
    fail_under: int = 0,
    elapsed_s: Optional[float] = None,
) -> Dict[str, Any]:
    """Score one case from a model (or fixture) reply."""
    expected = case.get("expected") if isinstance(case.get("expected"), dict) else case
    catalog = case.get("catalog") if isinstance(case.get("catalog"), dict) else {}
    report = validate_ai_response(
        response,
        known_tasks=catalog.get("tasks"),
        known_times=catalog.get("times"),
        cursor_lo=catalog.get("cursor_lo"),
        cursor_hi=catalog.get("cursor_hi"),
    )
    blob = str(response or "").lower()
    got_findings = [
        ft for ft in (expected.get("finding_types") or [])
        if str(ft).lower() in blob
    ]
    scored = score_benchmark_case(
        expected,
        actual_finding_ids=got_findings,
        actual_tasks=[
            str(c.get("value")) for c in (report.get("claims") or [])
            if isinstance(c, dict) and c.get("kind") == "task"
        ],
        actual_tools=list(tools or []),
        actual_conclusion=response,
        validation=report,
    )
    scored["id"] = case.get("id") or expected.get("id")
    floor = int(expected.get("pass_under") or fail_under or 70)
    scored["pass"] = int(scored.get("overall") or 0) >= floor and bool(
        report.get("ok", True) or not (expected.get("forbidden") or {})
    )
    if expected.get("forbidden", {}).get("invented_task_names") and not report.get("ok"):
        invented = any(
            c.get("kind") == "task" and not c.get("ok")
            for c in (report.get("claims") or [])
            if isinstance(c, dict)
        )
        if invented:
            scored["pass"] = False
    if expected.get("forbidden", {}).get("out_of_scope_timestamps"):
        oos = any(
            c.get("kind") == "jump" and not c.get("ok")
            for c in (report.get("claims") or [])
            if isinstance(c, dict)
        )
        if oos:
            scored["pass"] = False
    if fail_under and int(scored.get("overall") or 0) < int(fail_under):
        scored["pass"] = False
    scored["validation"] = report
    if elapsed_s is not None:
        scored["elapsed_s"] = round(float(elapsed_s), 2)
    scored["tools"] = list(tools or [])
    return scored


def run_offline_benchmark(
    dataset_path: Any,
    *,
    fail_under: int = 0,
) -> Dict[str, Any]:
    """Score fixture responses in a dataset (no live model calls)."""
    from datetime import datetime, timezone
    cases = load_benchmark_dataset(str(dataset_path))
    rows: List[Dict[str, Any]] = []
    for case in cases:
        actual = case.get("actual") if isinstance(case.get("actual"), dict) else {}
        response = str(actual.get("response") or case.get("response") or "")
        tools = list(actual.get("tools") or case.get("tools") or [])
        rows.append(score_benchmark_response(
            case, response=response, tools=tools, fail_under=fail_under,
        ))
    run_id = datetime.now(timezone.utc).strftime("%Y-%m-%d-%H%M%S")
    failed = [r for r in rows if not r.get("pass")]
    return {
        "run_id": run_id,
        "mode": "offline",
        "rows": rows,
        "failed": failed,
        "report": format_benchmark_report(run_id, rows),
        "ok": not failed,
    }


def run_live_benchmark(
    dataset_path: Any,
    models: Sequence[str],
    *,
    complete: Callable[..., Dict[str, Any]],
    fail_under: int = 0,
) -> Dict[str, Any]:
    """Score live model replies. *complete(query, findings_text, model, case)*."""
    from datetime import datetime, timezone
    ids = [str(m).strip() for m in (models or []) if str(m).strip()]
    if not ids:
        raise ValueError("live benchmark needs at least one model id")
    cases = load_benchmark_dataset(str(dataset_path))
    run_id = datetime.now(timezone.utc).strftime("%Y-%m-%d-%H%M%S")
    per_model: List[Dict[str, Any]] = []
    for model in ids:
        rows: List[Dict[str, Any]] = []
        error = ""
        for case in cases:
            query = str(case.get("question") or "").strip() or "Investigate the main problem."
            findings = benchmark_prompt_context(case)
            try:
                turn = complete(query, findings, model, case) or {}
            except Exception as exc:
                error = str(exc)
                turn = {"content": "", "tool_calls": [], "elapsed_s": 0, "error": error}
            if not isinstance(turn, dict):
                turn = {"content": str(turn or "")}
            content = str(turn.get("content") or "")
            raw_calls = turn.get("tool_calls") or []
            names: List[str] = []
            for c in raw_calls:
                if isinstance(c, dict):
                    name = str(c.get("name") or "")
                    if name:
                        names.append(name)
                elif c:
                    names.append(str(c))
            row = score_benchmark_response(
                case,
                response=content,
                tools=names,
                fail_under=fail_under,
                elapsed_s=turn.get("elapsed_s"),
            )
            if turn.get("error"):
                row["error"] = str(turn.get("error"))
                row["pass"] = False
            rows.append(row)
        failed = [r for r in rows if not r.get("pass")]
        per_model.append({
            "model": model,
            "category": benchmark_model_category(model),
            "run_id": run_id,
            "rows": rows,
            "failed": failed,
            "report": format_benchmark_report(f"{run_id}-{model}", rows),
            "ok": not failed and not error,
            "error": error,
        })
    return {
        "run_id": run_id,
        "mode": "live",
        "models": per_model,
        "ok": all(m.get("ok") for m in per_model),
        "report": "".join(m["report"] for m in per_model),
    }


def format_benchmark_markdown(
    *,
    offline: Optional[dict] = None,
    live: Optional[dict] = None,
    dataset: str = "tests/ai",
) -> str:
    """Markdown report for AI_BENCHMARK.md (offline scorer + optional live models)."""
    from datetime import datetime, timezone
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    lines = [
        "# AI Benchmark results",
        "",
        f"Generated: {stamp}",
        f"Dataset: `{dataset}`",
        "",
        "Live `--config` suite XML scores a real endpoint. Offline rows score the canned "
        "`response` fields in `dataset.json` and gate the scorer, not a model.",
        "",
    ]
    part_keys = (
        "finding", "evidence", "tool_use", "root_cause", "calibration", "safety",
    )

    def _table(rows: Sequence[dict]) -> List[str]:
        out = [
            "| Case | Overall | Finding | Evidence | Tool use | Root cause | Calibration | Safety | Result |",
            "|---|---:|---:|---:|---:|---:|---:|---:|---|",
        ]
        for row in rows:
            parts = row.get("parts") or {}
            flag = "ERROR" if row.get("error") else (
                "PASS" if row.get("pass") else "FAIL"
            )
            cells = [
                str(row.get("id") or "?"),
                str(row.get("overall") or 0),
            ]
            cells.extend(str(parts.get(k, "")) for k in part_keys)
            cells.append(flag)
            out.append("| " + " | ".join(cells) + " |")
        if rows:
            avg = int(round(sum(int(r.get("overall") or 0) for r in rows) / len(rows)))
            out.extend(["", f"**Overall {avg}**"])
        return out

    if offline:
        lines.extend([
            "## Offline fixture scorer",
            "",
            f"Run `{offline.get('run_id') or ''}` — no live model.",
            "",
        ])
        lines.extend(_table(offline.get("rows") or []))
        lines.append("")
    if live:
        blocks = list(live.get("models") or [])
        if blocks:
            lines.extend([
                "## Comparison",
                "",
                "| Model | Category | Overall | Pass | Mean latency |",
                "|---|---|---:|---:|---:|",
            ])
            for block in blocks:
                rows = list(block.get("rows") or [])
                n = len(rows)
                avg = int(round(sum(int(r.get("overall") or 0) for r in rows) / n)) if n else 0
                passed = sum(1 for r in rows if r.get("pass"))
                lat = [
                    float(r.get("elapsed_s") or 0)
                    for r in rows if r.get("elapsed_s") is not None
                ]
                mean_lat = f"{sum(lat) / len(lat):.1f}s" if lat else "—"
                lines.append(
                    f"| `{block.get('model') or '?'}` | "
                    f"{block.get('category') or ''} | {avg} | "
                    f"{passed}/{n} | {mean_lat} |"
                )
            lines.extend([
                "",
                "| Model | Finding | Evidence | Tool use | Root cause | Calibration | Safety |",
                "|---|---:|---:|---:|---:|---:|---:|",
            ])
            for block in blocks:
                rows = list(block.get("rows") or [])
                n = max(len(rows), 1)
                parts_avg = {}
                for key in part_keys:
                    parts_avg[key] = int(round(sum(
                        int((r.get("parts") or {}).get(key) or 0) for r in rows
                    ) / n)) if rows else 0
                cells = [f"`{block.get('model') or '?'}`"]
                cells.extend(str(parts_avg[k]) for k in part_keys)
                lines.append("| " + " | ".join(cells) + " |")
            lines.append("")
        lines.extend(["## Live models", ""])
        for block in live.get("models") or []:
            model = str(block.get("model") or "")
            cat = str(block.get("category") or benchmark_model_category(model))
            lines.extend([
                f"### `{model}`",
                "",
                f"{cat}. Run `{block.get('run_id') or live.get('run_id') or ''}`.",
                "",
            ])
            if block.get("error"):
                lines.extend([f"Error: {block['error']}", ""])
            lines.extend(_table(block.get("rows") or []))
            row_errors = [
                (str(r.get("id") or "?"), str(r.get("error") or "").strip())
                for r in (block.get("rows") or [])
                if r.get("error")
            ]
            if row_errors:
                first = row_errors[0][1]
                n_err = len(row_errors)
                snippet = first.split("\n", 1)[0][:240]
                lines.extend([
                    "",
                    f"{n_err}/{len(block.get('rows') or [])} cases returned an API error "
                    f"(first: {snippet}).",
                ])
            lat = [
                float(r.get("elapsed_s") or 0)
                for r in (block.get("rows") or [])
                if r.get("elapsed_s") is not None
            ]
            if lat:
                avg_s = sum(lat) / len(lat)
                lines.extend(["", f"Mean latency: **{avg_s:.1f}s** / case."])
            lines.append("")
    if not offline and not live:
        lines.append("_No runs recorded._")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"
