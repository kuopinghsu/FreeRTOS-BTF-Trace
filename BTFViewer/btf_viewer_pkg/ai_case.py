"""Investigation Case lifecycle: hypotheses, evidence graph, quality, validation.

Host-side (deterministic) layer on top of Analysis Findings / tool results.
Keep behaviour in sync with ``web/src/utils/aiCase.js``.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

HYPOTHESIS_STATUSES: Tuple[str, ...] = (
    "supported", "possible", "rejected", "need_evidence",
)
EVIDENCE_QUALITY_BANDS: Tuple[str, ...] = (
    "strong", "medium-high", "medium", "weak", "insufficient",
)
INVESTIGATION_MODES: Tuple[str, ...] = (
    "quick", "diagnose", "compare", "optimize", "report",
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
        "local": "Local",
        "cloud_safe": "Cloud",
        "sensitive": "Sensitive",
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
    flags: List[str] = []
    for key in ("migrations", "migration_rate", "blocking", "wcet"):
        try:
            a = float(cur.get(key))
            b = float(prev.get(key))
        except (TypeError, ValueError):
            continue
        if b == 0:
            continue
        ratio = a / b
        if ratio >= 2.0:
            flags.append(f"{key} {a:g} vs typical {b:g} (×{ratio:.1f})")
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
        "resembles_previous": resembles,
        "message": (
            f"This resembles the {issue} issue"
            + (f" seen in {build}" if build else "")
            if resembles else
            ("No historical match" if not prev else "Within historical range")
        ),
    }


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
) -> Dict[str, Any]:
    cap = infer_model_capabilities(
        model_name, endpoint_is_local=endpoint_is_local,
    )
    cap["chat"] = "yes" if chat_ok else "no"
    if tool_call_ok is True:
        cap["tool_calling"] = "yes"
    elif tool_call_ok is False:
        cap["tool_calling"] = "partial"
    return cap


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
        expected = case.get("expected") if isinstance(case.get("expected"), dict) else case
        actual = case.get("actual") if isinstance(case.get("actual"), dict) else {}
        response = str(actual.get("response") or case.get("response") or "")
        catalog = actual.get("catalog") or case.get("catalog") or {}
        report = validate_ai_response(
            response,
            known_tasks=catalog.get("tasks"),
            known_times=catalog.get("times"),
            cursor_lo=catalog.get("cursor_lo"),
            cursor_hi=catalog.get("cursor_hi"),
        )
        scored = score_benchmark_case(
            expected,
            actual_finding_ids=list(expected.get("finding_types") or []) if (
                any(
                    str(ft).lower() in response.lower()
                    for ft in (expected.get("finding_types") or [])
                )
            ) else [],
            actual_tasks=report.get("claims") and [
                str(c.get("value")) for c in report["claims"]
                if isinstance(c, dict) and c.get("kind") == "task"
            ] or [],
            actual_tools=list(actual.get("tools") or case.get("tools") or []),
            actual_conclusion=response,
            validation=report,
        )
        # If finding types appear in the response, treat them as identified.
        if expected.get("finding_types"):
            blob = response.lower()
            got = [
                ft for ft in expected["finding_types"]
                if str(ft).lower() in blob
            ]
            scored = score_benchmark_case(
                expected,
                actual_finding_ids=got,
                actual_tasks=[
                    str(c.get("value")) for c in (report.get("claims") or [])
                    if isinstance(c, dict) and c.get("kind") == "task"
                ],
                actual_tools=list(actual.get("tools") or case.get("tools") or []),
                actual_conclusion=response,
                validation=report,
            )
        scored["id"] = case.get("id") or expected.get("id")
        scored["pass"] = (
            int(scored.get("overall") or 0) >= int(expected.get("pass_under") or fail_under or 70)
            and bool(report.get("ok", True) or not (expected.get("forbidden") or {}))
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
        rows.append(scored)
    run_id = datetime.now(timezone.utc).strftime("%Y-%m-%d-%H%M%S")
    failed = [r for r in rows if not r.get("pass")]
    return {
        "run_id": run_id,
        "rows": rows,
        "failed": failed,
        "report": format_benchmark_report(run_id, rows),
        "ok": not failed,
    }
