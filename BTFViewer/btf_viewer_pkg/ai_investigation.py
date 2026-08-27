"""Investigation plan, evidence chain, baselines, and CI regression helpers.

Keep behaviour in sync with ``web/src/utils/aiInvestigation.js``.
"""
from __future__ import annotations

import json
import hashlib
import re
from typing import Any, Dict, List, NamedTuple, Optional, Sequence, Tuple

from .ai_case import (
    INVESTIGATION_SCOPE_OPTIONS,
    build_evidence_graph,
    build_investigation_case,
    compute_evidence_coverage,
    compute_evidence_quality,
    enrich_hypotheses,
    evidence_graph_mermaid,
    evidence_quality_from_score,
    falsification_checks,
    format_confidence_evolution,
    format_coverage_count_lines,
    format_quality_flag_lines,
    format_experiment_verdict,
    historical_knowledge_for_finding,
    mermaid_label_with_time,
)

# Default checklist shown while Investigate / Root cause / agent templates run.
INVESTIGATION_PLAN_STEPS: Tuple[Tuple[str, str], ...] = (
    ("findings", "Read Analysis Findings"),
    ("hypotheses", "Rank hypotheses"),
    ("metrics", "Query metrics / timeline"),
    ("narrow", "Narrow cursors / zoom"),
    ("related", "Inspect related tasks / sync"),
    ("validate", "Validate root cause"),
    ("recommend", "Recommend mitigation"),
)

# Tools that mark plan steps complete (name → step ids).
_TOOL_STEP_MAP: Dict[str, Tuple[str, ...]] = {
    "investigate": ("findings", "hypotheses"),
    "detect_anomalies": ("findings",),
    "query_raw_metric": ("metrics",),
    "search_timeline": ("metrics",),
    "correlate_events": ("metrics", "related"),
    "find_critical_path": ("metrics", "validate"),
    "compare_performance": ("metrics", "validate"),
    "trigger_compare": ("metrics", "related"),
    "set_cursors": ("narrow",),
    "zoom_to_range": ("narrow",),
    "highlight_task": ("related",),
    "open_corridor_inspector": ("related",),
    "add_annotation": ("validate",),
    "bookmark_finding": ("validate",),
    "check_budget": ("metrics", "validate"),
    "optimize": ("recommend",),
    "regression_explain": ("validate", "recommend"),
    "what_if": ("recommend",),
    "optimize_experiment": ("recommend",),
    "analyze_traces": ("metrics", "validate"),
    "investigation_replay": ("validate",),
    "generate_report": ("recommend",),
    "export_report": ("recommend",),
    "explain_finding": ("findings", "hypotheses"),
    "interpret_query": ("findings",),
    "validate_experiment": ("validate", "recommend"),
    "manage_hypotheses": ("hypotheses", "validate"),
    "plan_investigation": ("findings", "hypotheses"),
    "suggest_scope": ("findings", "narrow"),
    "detect_contradictions": ("validate",),
    "assess_evidence_sufficiency": ("validate",),
    "cluster_findings": ("findings",),
    "generate_fingerprint": ("findings",),
    "find_similar_investigations": ("recommend",),
    "regression_localize": ("metrics", "validate"),
    "build_causal_chain": ("validate",),
    "generate_experiment_plan": ("recommend",),
    "record_experiment_outcome": ("validate", "recommend"),
    "score_investigation": ("validate",),
    "analyze_temporal_causality": ("validate",),
    "build_task_dependency_graph": ("validate",),
    "decompose_response_time": ("metrics", "validate"),
    "rank_root_causes": ("hypotheses", "validate"),
    "verify_claim": ("validate",),
    "challenge_conclusion": ("validate",),
    "investigation_memory": ("recommend",),
    "cluster_incidents": ("findings",),
    "close_investigation": ("validate", "recommend"),
    "analyze_distribution": ("metrics",),
    "analyze_periodicity": ("metrics",),
    "summarize_investigation_context": ("validate",),
}

# Tools whose results refresh the Evidence & Validation log. Keep in sync with
# web/src/utils/aiInvestigation.js EVIDENCE_PANEL_TOOLS.
EVIDENCE_PANEL_TOOLS: Tuple[str, ...] = (
    "investigate",
    "correlate_events",
    "find_critical_path",
    "detect_priority_inversion",
    "compare_performance",
    "search_timeline",
    "explain_finding",
    "interpret_query",
    "validate_experiment",
    "manage_hypotheses",
    "plan_investigation",
    "suggest_scope",
    "detect_contradictions",
    "assess_evidence_sufficiency",
    "cluster_findings",
    "generate_fingerprint",
    "find_similar_investigations",
    "regression_localize",
    "build_causal_chain",
    "generate_experiment_plan",
    "record_experiment_outcome",
    "score_investigation",
    "analyze_temporal_causality",
    "build_task_dependency_graph",
    "decompose_response_time",
    "rank_root_causes",
    "verify_claim",
    "challenge_conclusion",
    "investigation_memory",
    "cluster_incidents",
    "close_investigation",
    "analyze_distribution",
    "analyze_periodicity",
    "summarize_investigation_context",
)

# Agent templates that need investigate-stage tools from the first turn.
_EVIDENCE_STAGE_TEMPLATES = frozenset({
    "auto_investigate", "investigate", "root_cause", "verify",
})

_AGENT_TEMPLATE_IDS = frozenset({
    "investigate", "root_cause", "verify", "what_if", "optimize",
    "diagnostic_report", "auto_investigate", "explain_finding",
})

_FINDING_ID_RE = re.compile(r"^[a-z][a-z0-9_]{0,47}$")

# CI gate defaults (A = candidate, B = baseline). Positive Δ on A−B means worse
# for migrations / missed ticks; negative load-balance score means worse.
DEFAULT_REGRESSION_RULES: Tuple[Dict[str, Any], ...] = (
    {
        "id": "migrations",
        "label": "Migrations (total)",
        "metric": "migrations",
        "worse_when": "increase_pct",
        "threshold": 20.0,
    },
    {
        "id": "load_balance",
        "label": "Load Balance Score",
        "metric": "load_balance_score",
        "worse_when": "decrease_abs",
        "threshold": 10.0,
    },
    {
        "id": "missed_ticks",
        "label": "Missed ticks (est.)",
        "metric": "missed_ticks",
        "worse_when": "increase_abs",
        "threshold": 1.0,
    },
    {
        "id": "migrated_tasks",
        "label": "Migrated tasks",
        "metric": "migrated_tasks",
        "worse_when": "increase_pct",
        "threshold": 25.0,
    },
)


def is_agent_template(template_id: str) -> bool:
    return str(template_id or "").strip() in _AGENT_TEMPLATE_IDS


def elevate_guide_stage_for_template(stage: str, template_id: str = "") -> str:
    """Promote triage/scope to investigate for Start Investigation-style templates.

    Balanced tool catalogs gate Preferred evidence tools behind the guide stage.
    Without this, auto_investigate starts in triage and never offers
    correlate_events / find_critical_path on the first turn.
    """
    sid = str(stage or "").strip().lower()
    if not sid or sid in ("idle", "start"):
        sid = "triage"
    tid = str(template_id or "").strip()
    if tid in _EVIDENCE_STAGE_TEMPLATES and sid in ("triage", "scope"):
        return "investigate"
    return sid


def max_tool_rounds_for_template(template_id: str = "", default: int = 4) -> int:
    """Allow deeper tool loops for Investigate-style templates."""
    return 8 if is_agent_template(template_id) else int(default)


def default_investigation_plan(goal: str = "") -> Dict[str, Any]:
    """Return a fresh Investigation Plan structure for the UI."""
    return {
        "goal": (goal or "Investigate the main performance problem").strip(),
        "steps": [
            {"id": sid, "label": label, "status": "pending"}  # pending|active|done
            for sid, label in INVESTIGATION_PLAN_STEPS
        ],
    }


def mark_plan_steps_from_tools(
    plan: Optional[Dict[str, Any]],
    tool_names: Sequence[str],
) -> Dict[str, Any]:
    """Advance plan statuses from tool names that already ran."""
    out = plan if isinstance(plan, dict) else default_investigation_plan()
    steps = list(out.get("steps") or [])
    by_id = {str(s.get("id")): s for s in steps if isinstance(s, dict)}
    done_ids = set()
    for name in tool_names:
        for sid in _TOOL_STEP_MAP.get(str(name or ""), ()):
            done_ids.add(sid)
            step = by_id.get(sid)
            if step is not None:
                step["status"] = "done"
    # Activate the first pending step.
    activated = False
    for step in steps:
        if step.get("status") == "done":
            continue
        if not activated:
            step["status"] = "active"
            activated = True
        else:
            step["status"] = "pending"
    if not activated and steps:
        # All done — keep last as done.
        pass
    out["steps"] = steps
    return out


def complete_investigation_plan(
    plan: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
    """Mark every plan step done (final assistant answer / investigation finished).

    Investigate prompts ask for mitigation in the reply text; that does not
    always call ``export_report``, so Recommend mitigation would otherwise stay
    unchecked.
    """
    out = plan if isinstance(plan, dict) else default_investigation_plan()
    steps = []
    for step in out.get("steps") or []:
        if not isinstance(step, dict):
            continue
        item = dict(step)
        item["status"] = "done"
        steps.append(item)
    out = dict(out)
    out["steps"] = steps
    return out


def slug_finding_id(title: str, used: Optional[set] = None) -> str:
    """Stable-ish id from a finding title."""
    base = re.sub(r"[^a-z0-9]+", "_", str(title or "finding").lower()).strip("_")
    if not base:
        base = "finding"
    base = base[:40]
    if not _FINDING_ID_RE.match(base):
        base = "finding"
    used = used if used is not None else set()
    cand = base
    n = 2
    while cand in used:
        cand = f"{base}_{n}"
        n += 1
    used.add(cand)
    return cand


_JUMP_IN_TEXT_RE = re.compile(r"jump:([0-9]+(?:\.[0-9]+)?)", re.IGNORECASE)


def _promote_jump_times_from_text(item: Dict[str, Any]) -> None:
    """If a finding text cites jump:TIME but evidence has no times, add one."""
    evidence = [
        dict(e) for e in (item.get("evidence") or []) if isinstance(e, dict)
    ]
    if any(e.get("time") is not None for e in evidence):
        item["evidence"] = evidence
        return
    blob = f"{item.get('title') or ''} {item.get('text') or ''}"
    m = _JUMP_IN_TEXT_RE.search(blob)
    if not m:
        item["evidence"] = evidence
        return
    try:
        raw = float(m.group(1))
        t: Any = int(raw) if raw.is_integer() else raw
    except (TypeError, ValueError):
        item["evidence"] = evidence
        return
    evidence.append({"label": "finding text", "time": t})
    item["evidence"] = evidence


def enrich_findings_with_ids(findings: Sequence[dict]) -> List[dict]:
    """Copy findings and ensure each has a unique ``id`` field."""
    used: set = set()
    out: List[dict] = []
    for f in findings or []:
        item = dict(f or {})
        fid = str(item.get("id") or "").strip()
        if not fid or not _FINDING_ID_RE.match(fid) or fid in used:
            fid = slug_finding_id(str(item.get("title") or "finding"), used)
        else:
            used.add(fid)
        item["id"] = fid
        _promote_jump_times_from_text(item)
        out.append(item)
    return out


def format_findings_evidence_chain(findings: Sequence[dict]) -> str:
    """Markdown evidence block for AI context / UI."""
    lines = ["## Evidence", ""]
    if not findings:
        lines.append("_No findings in scope._")
        return "\n".join(lines)
    for f in findings:
        sev = str(f.get("severity", "info")).upper()
        fid = str(f.get("id") or "")
        title = str(f.get("title") or "Finding")
        text = str(f.get("text") or "")
        lines.append(f"- **[{sev}] {title}** (`id={fid}`)")
        lines.append(f"  - {text}")
        evidence = f.get("evidence") or []
        for ev in evidence:
            if isinstance(ev, dict):
                label = str(ev.get("label") or ev.get("text") or "evidence")
                t = ev.get("time")
                if t is not None:
                    lines.append(f"  - {label}: jump:{t}")
                else:
                    lines.append(f"  - {label}")
            else:
                lines.append(f"  - {ev}")
    return "\n".join(lines)


def resolve_finding(
    findings: Sequence[dict],
    finding_id: str = "",
) -> Optional[dict]:
    """Resolve by id, 1-based index, or title substring."""
    items = enrich_findings_with_ids(findings)
    want = str(finding_id or "").strip()
    if not want:
        # Prefer first warning/error, else first finding.
        for f in items:
            if f.get("severity") in ("warning", "error"):
                return f
        return items[0] if items else None
    low = want.lower()
    for f in items:
        if str(f.get("id") or "").lower() == low:
            return f
    if want.isdigit():
        idx = int(want) - 1
        if 0 <= idx < len(items):
            return items[idx]
    for f in items:
        if low in str(f.get("title") or "").lower():
            return f
    return None


def build_investigate_context(
    findings: Sequence[dict],
    finding_id: str = "",
    *,
    depth: int = 2,
) -> Dict[str, Any]:
    """Structured investigation graph for the ``investigate`` tool."""
    depth = max(1, min(5, int(depth or 2)))
    items = enrich_findings_with_ids(findings)
    focus = resolve_finding(items, finding_id)
    if focus is None:
        return {
            "ok": False,
            "message": "No Analysis Findings in scope",
            "findings": [],
            "focus": None,
            "hypotheses": [],
            "alternatives": [],
            "suggested_tools": [],
            "plan": default_investigation_plan(),
            "evidence_chain": format_findings_evidence_chain([]),
        }

    title = str(focus.get("title") or "")
    text = str(focus.get("text") or "")
    sev = str(focus.get("severity") or "info")
    hypotheses = _hypotheses_for_finding(title, text)
    alternatives = _alternatives_from_hypotheses(hypotheses)
    suggested = _suggested_tools_for_finding(title, text, depth)
    related = [
        {"id": f.get("id"), "severity": f.get("severity"), "title": f.get("title")}
        for f in items
        if f.get("id") != focus.get("id")
    ][:8]
    plan = default_investigation_plan(goal=f"Investigate: {title}")
    plan = mark_plan_steps_from_tools(plan, ["investigate"])
    chain = build_root_cause_chain(focus)
    anomalies = detect_anomalies(items, limit=max(3, depth + 2))
    finding = {
        "id": focus.get("id"),
        "severity": sev,
        "title": title,
        "text": text,
        "evidence": list(focus.get("evidence") or []),
        "task": focus.get("task") or _guess_task_name(text),
    }
    hyps = enrich_hypotheses(
        hypotheses[: max(1, depth + 1)],
        evidence=finding.get("evidence"),
        alternatives=alternatives[: max(1, depth + 1)],
    )
    graph = {
        "finding": finding,
        "related_findings": related,
        "hypotheses": hyps,
        "alternatives": alternatives[: max(1, depth + 1)],
        "suggested_tools": suggested,
        "depth": depth,
        "evidence_chain": format_findings_evidence_chain([focus]),
        "root_cause_chain": chain,
        "ranked_anomalies": (anomalies.get("anomalies") or [])[: max(3, depth)],
        "plan": plan,
    }
    score_data = compute_evidence_score(
        graph["finding"].get("evidence"),
        alternatives=graph.get("alternatives"),
        evidence_chain=graph.get("evidence_chain"),
    )
    graph["evidence_score"] = score_data["score"]
    graph["evidence_score_breakdown"] = score_data["breakdown"]
    quality = compute_evidence_quality(
        score=score_data["score"],
        breakdown=score_data["breakdown"],
        evidence=graph["finding"].get("evidence"),
        alternatives=graph.get("alternatives"),
        evidence_chain=graph.get("evidence_chain"),
    )
    graph["evidence_quality"] = quality
    graph["evidence_coverage"] = compute_evidence_coverage(
        evidence=graph["finding"].get("evidence"),
    )
    graph["evidence_graph"] = build_evidence_graph(
        finding,
        evidence=finding.get("evidence"),
        hypotheses=hyps,
        chain=chain,
    )
    graph["falsification"] = falsification_checks(finding)
    graph["historical_knowledge"] = historical_knowledge_for_finding(finding)
    graph["investigation_case"] = build_investigation_case(
        graph,
        score_data=score_data,
    )
    return {
        "ok": True,
        "message": (
            f"Investigation context for {focus.get('id')} "
            f"({len(hypotheses)} hypotheses, {len(suggested)} suggested tools)"
        ),
        **graph,
    }


def _alternatives_from_hypotheses(
    hypotheses: Sequence[dict],
) -> List[Dict[str, str]]:
    """Ranked alternative explanations derived from heuristic hypotheses."""
    alts: List[Dict[str, str]] = []
    for i, h in enumerate(hypotheses or []):
        if not isinstance(h, dict):
            continue
        hyp = str(h.get("hypothesis") or "").strip()
        if not hyp:
            continue
        why = str(h.get("why") or "").strip()
        status = "plausible" if i == 0 else "untested"
        alts.append({"hypothesis": hyp, "status": status, "why": why})
    return alts


def _hypotheses_for_finding(title: str, text: str) -> List[Dict[str, str]]:
    blob = f"{title} {text}".lower()
    hyps: List[Dict[str, str]] = []
    def add(h: str, why: str) -> None:
        hyps.append({"hypothesis": h, "why": why})

    if "thrash" in blob or "migration" in blob or "bounc" in blob:
        add("Core thrashing / lock bounce", "High migration or bounce metrics")
        add("Missing affinity pin", "Equal-priority fan-out across cores")
    if "block" in blob or "latency" in blob or "dispatch" in blob:
        add("Off-CPU blocking / mutex wait", "Blocking gaps dominate latency")
        add("Preemption chain interference", "Higher-priority work stretches wait")
    if "inversion" in blob or "l/m/h" in blob or "inherit" in blob:
        add("Priority inversion on shared mutex", "L/M/H geometry in findings")
    if "wcet" in blob or "cpu" in blob or "execution" in blob or "spike" in blob:
        add("Long execution slices / WCET spike", "Max vs typical execution diverge")
        add("Interrupt or critical-section stretch", "Unexplained Max growth")
    if "load" in blob or "imbalance" in blob or "balance" in blob:
        add("Uneven core placement", "Load Balance Score / σ warning")
    if "tick" in blob or "missed" in blob:
        add("Tick health / tickless idle gaps", "TICK CV or missed ticks")
    if "deadline" in blob or "budget" in blob:
        add("Deadline or CPU-budget breach", "Configured thresholds exceeded")
    if not hyps:
        add("Primary finding needs metric drill-down", "No specialised heuristic match")
    return hyps


def _suggested_tools_for_finding(
    title: str, text: str, depth: int,
) -> List[Dict[str, Any]]:
    blob = f"{title} {text}".lower()
    tools: List[Dict[str, Any]] = []
    task = _guess_task_name(text)

    def add(name: str, arguments: Dict[str, Any], reason: str) -> None:
        tools.append({"name": name, "arguments": arguments, "reason": reason})

    if task:
        if "block" in blob or "inversion" in blob or "latency" in blob:
            add("query_raw_metric", {"task": task, "metric": "blocking"},
                "Inspect blocking gaps")
            add("query_raw_metric", {"task": task, "metric": "priority_inheritance"},
                "Check inherit episodes")
        if "wcet" in blob or "cpu" in blob or "execution" in blob or "spike" in blob:
            add("query_raw_metric", {"task": task, "metric": "execution"},
                "Inspect execution slices")
        if "migrat" in blob or "thrash" in blob or "bounc" in blob:
            add("query_raw_metric", {"task": task, "metric": "migrations"},
                "Inspect migrations")
            add("open_corridor_inspector", {}, "Open migration inspector")
        add("highlight_task", {"task_name_or_id": task}, "Highlight victim task")
        add("search_timeline", {"query": task, "mode": "contains"},
            "Locate task on timeline")
    else:
        add("query_raw_metric", {"task": "*", "metric": "findings"},
            "Re-read findings lines")
        add("search_timeline", {"query": "mutex", "mode": "sti"},
            "Search sync activity")
    if depth >= 2:
        add("detect_anomalies", {"limit": 8}, "Rank Critical/Warning anomalies")
    if task and depth >= 2:
        add("correlate_events", {"task": task}, "Cross-task event correlation")
    if depth >= 3:
        add("trigger_compare", {}, "Compare two open tabs if available")
        add("compare_performance", {}, "Structured A vs B performance deltas")
    if depth >= 4:
        add("generate_report", {"report_type": "root_cause"}, "Structured RCA report")
        add("export_report", {"format": "html"}, "Save diagnostic report")
    return tools[: max(3, depth * 2)]


_INV_TASK_TOKEN_RE = re.compile(
    r"\b([A-Za-z_][\w]*(?:\[[0-9]+\])?)\b"
)


def _guess_task_name(text: str) -> str:
    """Best-effort task token from finding text (e.g. CS[28], High[268])."""
    # Prefer Name[id] forms.
    bracketed = re.findall(r"\b[A-Za-z_][\w]*\[[0-9]+\]", text or "")
    for tok in bracketed:
        low = tok.lower()
        if low.startswith("core") or low in ("tick",):
            continue
        return tok
    for m in _INV_TASK_TOKEN_RE.finditer(text or ""):
        tok = m.group(1)
        low = tok.lower()
        if low in ("max", "min", "rate", "dwell", "ping", "load", "balance",
                     "score", "tick", "mode", "core", "mutex", "queue"):
            continue
        if "[" in tok:
            return tok
    return bracketed[0] if bracketed else ""


def snapshot_from_summary(summary: Dict[str, Any], *, name: str = "") -> Dict[str, Any]:
    """Baseline JSON payload from ``_trace_summary_snapshot``."""
    return {
        "version": 1,
        "name": name or "",
        "metrics": {
            "span_ns": summary.get("span_ns"),
            "tasks": summary.get("tasks"),
            "segments": summary.get("segments"),
            "migrations": summary.get("migrations"),
            "migrated_tasks": summary.get("migrated_tasks"),
            "load_balance_score": summary.get("load_balance_score"),
            "load_balance_sigma": summary.get("load_balance_sigma"),
            "missed_ticks": summary.get("missed_ticks"),
            "tick_health": summary.get("tick_health"),
            "context_switches": summary.get("context_switches"),
        },
    }


def load_baseline_json(path: str) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as fh:
        data = json.load(fh)
    if not isinstance(data, dict) or "metrics" not in data:
        raise ValueError("baseline JSON must contain a metrics object")
    return data


def save_baseline_json(path: str, snapshot: Dict[str, Any]) -> None:
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(snapshot, fh, indent=2, sort_keys=True)
        fh.write("\n")


def evaluate_regression(
    candidate: Dict[str, Any],
    baseline: Dict[str, Any],
    *,
    rules: Optional[Sequence[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """Compare candidate vs baseline metrics; return gate result.

    ``candidate`` / ``baseline`` may be summary snapshots or baseline JSON
    (with ``metrics``).
    """
    cand = candidate.get("metrics") if "metrics" in candidate else candidate
    base = baseline.get("metrics") if "metrics" in baseline else baseline
    cand = dict(cand or {})
    base = dict(base or {})
    checks: List[Dict[str, Any]] = []
    failed = False
    for rule in (rules or DEFAULT_REGRESSION_RULES):
        mid = str(rule.get("metric") or "")
        a = cand.get(mid)
        b = base.get(mid)
        status = "skip"
        detail = "missing metric"
        delta: Optional[float] = None
        if a is None or b is None:
            status = "skip"
        else:
            try:
                av = float(a)
                bv = float(b)
            except (TypeError, ValueError):
                status = "skip"
                detail = "non-numeric"
            else:
                thr = float(rule.get("threshold") or 0)
                mode = str(rule.get("worse_when") or "")
                if mode == "increase_pct":
                    if bv == 0:
                        delta = 100.0 if av > 0 else 0.0
                    else:
                        delta = 100.0 * (av - bv) / abs(bv)
                    if delta >= thr:
                        status = "fail"
                        failed = True
                        detail = f"+{delta:.1f}% (threshold {thr:g}%)"
                    else:
                        status = "pass"
                        detail = f"{delta:+.1f}% (threshold {thr:g}%)"
                elif mode == "decrease_abs":
                    delta = bv - av  # positive when candidate is worse (lower score)
                    if delta >= thr:
                        status = "fail"
                        failed = True
                        detail = f"dropped {delta:.1f} (threshold {thr:g})"
                    else:
                        status = "pass"
                        detail = f"Δ score {av - bv:+.1f} (threshold −{thr:g})"
                elif mode == "increase_abs":
                    delta = av - bv
                    if delta >= thr:
                        status = "fail"
                        failed = True
                        detail = f"+{delta:.1f} (threshold {thr:g})"
                    else:
                        status = "pass"
                        detail = f"{delta:+.1f} (threshold {thr:g})"
                else:
                    status = "skip"
                    detail = f"unknown rule {mode}"
        checks.append({
            "id": rule.get("id"),
            "label": rule.get("label") or mid,
            "status": status,
            "detail": detail,
            "candidate": a,
            "baseline": b,
            "delta": delta,
        })
    return {
        "ok": not failed,
        "failed": failed,
        "checks": checks,
        "summary": (
            "REGRESSION DETECTED" if failed else "No regression vs baseline"
        ),
    }


def format_regression_report(result: Dict[str, Any], *, title: str = "") -> str:
    lines = [
        "BTF AI / CI Analysis" + (f" — {title}" if title else ""),
        "",
        ("❌ " if result.get("failed") else "✅ ") + str(result.get("summary") or ""),
        "",
    ]
    for c in result.get("checks") or []:
        mark = {"pass": "✓", "fail": "✗", "skip": "·"}.get(c.get("status"), "?")
        lines.append(
            f"{mark} {c.get('label')}: {c.get('detail')} "
            f"(A={c.get('candidate')}, B={c.get('baseline')})"
        )
    lines.append("")
    lines.append(
        "CI status: " + ("FAILED" if result.get("failed") else "PASSED")
    )
    return "\n".join(lines) + "\n"


def append_wcet_anomaly_finding(
    findings: List[dict],
    spike_rows: Sequence[Tuple[str, float, float, int]],
    *,
    ratio_threshold: float = 5.0,
) -> List[dict]:
    """Append WCET Max/Avg spike anomalies.

    *spike_rows*: ``(name, avg_ns, max_ns, runs)``.
    """
    spikes = []
    for name, avg_ns, max_ns, runs in spike_rows:
        if runs < 5 or avg_ns <= 0:
            continue
        ratio = float(max_ns) / float(avg_ns)
        if ratio >= ratio_threshold:
            spikes.append(f"{name} (Max/Avg={ratio:.1f}×, n={runs})")
    if spikes:
        findings.append({
            "id": "wcet_anomaly",
            "severity": "warning",
            "title": "Anomaly: WCET spike vs typical execution",
            "text": (
                "Execution Max is much larger than Avg — multimodal or bursty "
                "slices: " + "; ".join(spikes[:5])
                + ". Open Execution Time and jump to Max."
            ),
            "evidence": [],
        })
    return findings


def append_migration_burst_anomaly(
    findings: List[dict],
    burst_rows: Sequence[Tuple[str, float, int]],
    *,
    rate_threshold: float = 10.0,
) -> List[dict]:
    """Append extreme migration-rate anomalies (rate ≥ *rate_threshold*/s)."""
    bursts = []
    for name, rate, n_mig in burst_rows:
        if rate >= rate_threshold and n_mig >= 10:
            bursts.append(f"{name} ({rate:.1f}/s, Migr={n_mig})")
    if bursts:
        findings.append({
            "id": "migration_burst_anomaly",
            "severity": "warning",
            "title": "Anomaly: migration burst",
            "text": (
                "Migration rate far above thrash heuristic: "
                + "; ".join(bursts[:5])
                + ". Check Migration Heatmap for a short thrash window."
            ),
            "evidence": [],
        })
    return findings


_ANOMALY_ID_BOOST = frozenset({
    "wcet_anomaly", "migration_burst_anomaly", "thrashing", "blocking",
    "priority_inversion", "deadlines", "missed_ticks", "tick_health",
    "sync_bounce", "hot_pairs",
})
_SEV_RANK = {"error": 0, "warning": 1, "info": 2}


def detect_anomalies(
    findings: Sequence[dict],
    *,
    limit: int = 10,
) -> Dict[str, Any]:
    """Rank Analysis Findings as Critical / Warning / Info anomalies."""
    limit = max(1, min(40, int(limit or 10)))
    items = enrich_findings_with_ids(findings)
    ranked: List[Tuple[Any, ...]] = []
    for i, f in enumerate(items):
        sev = str(f.get("severity") or "info").lower()
        fid = str(f.get("id") or "")
        boost = 0 if fid in _ANOMALY_ID_BOOST else 1
        ranked.append((_SEV_RANK.get(sev, 3), boost, i, f))
    ranked.sort(key=lambda row: row[:3])
    anomalies: List[dict] = []
    counts = {"critical": 0, "warning": 0, "info": 0}
    for rank_i, (_s, _b, _i, f) in enumerate(ranked[:limit], start=1):
        sev = str(f.get("severity") or "info").lower()
        band = "critical" if sev == "error" else ("warning" if sev == "warning" else "info")
        counts[band] = counts.get(band, 0) + 1
        anomalies.append({
            "rank": rank_i,
            "band": band,
            "severity": sev,
            "id": f.get("id"),
            "title": f.get("title"),
            "text": f.get("text"),
            "task": f.get("task") or _guess_task_name(str(f.get("text") or "")),
            "evidence": list(f.get("evidence") or []),
        })
    return {
        "ok": True,
        "message": (
            f"{len(anomalies)} ranked anomal{'y' if len(anomalies) == 1 else 'ies'} "
            f"(critical={counts['critical']}, warning={counts['warning']}, "
            f"info={counts['info']})"
        ),
        "anomalies": anomalies,
        "counts": counts,
        "total_findings": len(items),
    }


_MERMAID_LABEL_STRIP_RE = re.compile(r'["\[\]{}()|]')


def _mermaid_safe_label(text: Any, limit: int = 96) -> str:
    """Strip mermaid delimiter characters so a label is safe as a node body."""
    cleaned = _MERMAID_LABEL_STRIP_RE.sub("", str(text or "").replace("\n", " ")).strip()
    cleaned = re.sub(r"\s+", " ", cleaned)
    return (cleaned or "Step")[:limit]


def investigation_tree_mermaid(
    chain: Optional[Sequence[Dict[str, Any]]] = None,
    hypotheses: Optional[Sequence[Dict[str, Any]]] = None,
) -> str:
    """Render a root-cause chain + hypotheses as a mermaid ``graph TD`` snippet.

    Rectangles are the ``root_cause_chain`` steps (in order); rounded nodes
    branch off the first (finding) step for each alternative hypothesis.
    Rendered the same way as any other diagram (``mermaid_block_html`` /
    ``formatAiMessageHtml``). Kept in sync with
    ``web/src/utils/aiInvestigation.js`` ``investigationTreeMermaid``.
    """
    chain_items = [c for c in (chain or []) if isinstance(c, dict)]
    hyp_items = [h for h in (hypotheses or []) if isinstance(h, dict)]
    if not chain_items and not hyp_items:
        return ""
    lines = ["graph TD"]
    node_ids: List[str] = []
    for i, step in enumerate(chain_items):
        nid = f"S{i}"
        label = mermaid_label_with_time(
            step.get("label") or f"Step {i + 1}", step.get("time"))
        lines.append(f"{nid}[{label}]")
        node_ids.append(nid)
    for i in range(1, len(node_ids)):
        lines.append(f"{node_ids[i - 1]} --> {node_ids[i]}")
    anchor = node_ids[0] if node_ids else None
    for j, h in enumerate(hyp_items):
        nid = f"H{j}"
        label = _mermaid_safe_label(h.get("hypothesis") or f"Hypothesis {j + 1}")
        lines.append(f"{nid}({label})")
        if anchor:
            lines.append(f"{anchor} --> {nid}")
    return "\n".join(lines)


def evidence_score_bar(score: Any, width: int = 10) -> str:
    """Text meter for the AI Evidence Score, e.g. ``████████░░ 82%``."""
    try:
        pct = max(0, min(100, int(round(float(score)))))
    except (TypeError, ValueError):
        pct = 0
    filled = max(0, min(width, int(round(width * pct / 100.0))))
    return "█" * filled + "░" * (width - filled) + f" {pct}%"


def compute_evidence_score(
    evidence: Optional[Sequence[Dict[str, Any]]] = None,
    *,
    alternatives: Optional[Sequence[Dict[str, Any]]] = None,
    evidence_chain: str = "",
    checks: Optional[Sequence[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """Heuristic 0-100 "AI Evidence Score" for an investigation conclusion.

    **Not a statistical confidence interval** — a coarse heuristic to help
    triage how much concrete evidence backs a conclusion (label it
    "AI Evidence Score — heuristic" in the UI). Kept in sync with
    ``web/src/utils/aiInvestigation.js`` ``computeEvidenceScore``.

    Factors:

    - +40 at least one evidence item carries a concrete ``time`` (jump:TIME)
    - +25 timeline correlation — evidence spans ≥2 kinds (``"kind: detail"``
      labels, as produced by ``correlate_events`` / ``find_critical_path``),
      or an evidence-chain narrative is present
    - +15 metric correlation — a verification checklist backs the
      conclusion (``compare_performance`` / ``check_budget`` style checks)
    - −5 per untested alternative hypothesis (max −15)
    - −10 no evidence at all (neither items nor a chain)
    """
    ev = [e for e in (evidence or []) if isinstance(e, dict)]
    alts = [a for a in (alternatives or []) if isinstance(a, dict)]
    chks = [c for c in (checks or []) if isinstance(c, dict)]
    chain_text = str(evidence_chain or "").strip()
    breakdown: List[Dict[str, Any]] = []
    score = 0

    has_times = any(e.get("time") is not None for e in ev)
    if has_times:
        score += 40
        breakdown.append({"label": "Direct evidence times (jump:TIME)", "delta": 40})

    kinds = set()
    for e in ev:
        label = str(e.get("label") or "")
        if ":" in label:
            kind = label.split(":", 1)[0].strip().lower()
            if kind:
                kinds.add(kind)
    has_timeline_corr = len(kinds) >= 2 or bool(chain_text)
    if has_timeline_corr:
        score += 25
        breakdown.append({"label": "Timeline correlation", "delta": 25})

    if chks:
        score += 15
        breakdown.append({"label": "Metric correlation", "delta": 15})

    untested = [
        a for a in alts
        if str(a.get("status") or "").lower() in (
            "untested", "need_evidence", "needs_evidence", "",
        )
    ]
    if untested:
        penalty = min(15, 5 * len(untested))
        score -= penalty
        breakdown.append({
            "label": f"{len(untested)} alternative(s) untested",
            "delta": -penalty,
        })

    if not ev and not chain_text:
        score -= 10
        breakdown.append({"label": "Missing direct evidence", "delta": -10})

    score = max(0, min(100, score))
    quality = evidence_quality_from_score(score, breakdown=breakdown)
    return {
        "score": score,
        "label": "AI Evidence Score — heuristic",
        "bar": evidence_score_bar(score),
        "breakdown": breakdown,
        "quality": quality,
    }


def build_root_cause_chain(finding: Optional[dict]) -> List[Dict[str, Any]]:
    """Heuristic Finding → cause steps for the Root Cause Chain UI/tool data."""
    if not finding:
        return []
    title = str(finding.get("title") or "")
    text = str(finding.get("text") or "")
    blob = f"{title} {text}".lower()
    task = str(finding.get("task") or "") or _guess_task_name(text)
    steps: List[Dict[str, Any]] = []

    def add(label: str, detail: str = "", *, kind: str = "step") -> None:
        steps.append({"kind": kind, "label": label, "detail": detail, "task": task})

    add(f"Finding: {title or finding.get('id') or 'unknown'}", text[:240], kind="finding")
    if task:
        add(f"Focus task {task}", "Extracted from finding text", kind="task")
    if "block" in blob or "latency" in blob or "dispatch" in blob:
        add("Off-CPU / blocking gap", "Inspect Blocking Time + STI wait")
        add("Synchronization hold", "Check mutex/semaphore owner")
    if "inversion" in blob or "l/m/h" in blob or "inherit" in blob:
        add("Priority relationship", "L/M/H or inherit episode")
        add("Likely priority inversion", "High confidence if PI episodes align", kind="cause")
    if "migrat" in blob or "thrash" in blob or "bounc" in blob:
        add("Core migration / thrash", "Corridor + migration rate")
        add("Likely affinity / lock bounce", kind="cause")
    if "wcet" in blob or "spike" in blob or "execution" in blob or "cpu" in blob:
        add("Execution / WCET spike", "Jump to Max slice")
        add("Likely long critical section or preemption stretch", kind="cause")
    if "deadline" in blob or "budget" in blob:
        add("Deadline / budget breach", kind="cause")
    if "tick" in blob or "missed" in blob:
        add("Tick health / missed ticks", kind="cause")
    if not any(s.get("kind") == "cause" for s in steps):
        add("Needs metric drill-down", "Call correlate_events / query_raw_metric", kind="cause")
    add("Verify on timeline", "set_cursors + zoom_to_range + highlight_task", kind="ui")
    return steps


def build_correlation_timeline(
    events: Sequence[dict],
    *,
    task: str = "",
    around_time: Optional[float] = None,
    window: float = 0.0,
    limit: int = 40,
) -> Dict[str, Any]:
    """Merge cross-metric events into a time-ordered correlation list."""
    limit = max(1, min(80, int(limit or 40)))
    rows: List[dict] = []
    for ev in events or []:
        if not isinstance(ev, dict):
            continue
        try:
            t = float(ev.get("time"))
        except (TypeError, ValueError):
            continue
        rows.append({
            "time": t,
            "kind": str(ev.get("kind") or ev.get("metric") or "event"),
            "detail": str(ev.get("detail") or ev.get("note") or ev.get("event") or ""),
            "task": str(ev.get("task") or task or ""),
            "core": ev.get("core") or "",
            "start": ev.get("start", t),
            "stop": ev.get("stop"),
            "duration": ev.get("duration", ev.get("gap")),
        })
        if rows[-1]["stop"] is None and rows[-1]["duration"] is not None:
            try:
                rows[-1]["stop"] = float(t) + float(rows[-1]["duration"])
            except (TypeError, ValueError):
                pass
    rows.sort(key=lambda r: r["time"])
    if around_time is not None and window and window > 0:
        lo = float(around_time) - float(window)
        hi = float(around_time) + float(window)
        rows = [r for r in rows if lo <= r["time"] <= hi]
    truncated = len(rows) > limit
    rows = rows[:limit]
    kinds = {r["kind"] for r in rows}
    score = 0.0
    if rows:
        score = min(0.99, 0.35 + 0.12 * max(0, len(kinds) - 1) + 0.01 * min(40, len(rows)))
    suggested: List[Dict[str, Any]] = []
    if rows:
        t0, t1 = rows[0]["time"], rows[-1]["time"]
        suggested.append({
            "name": "set_cursors",
            "arguments": {"timestamps": [t0, t1] if t1 != t0 else [t0]},
            "reason": "Bracket correlated window",
        })
        if t1 > t0:
            pad = max(1.0, (t1 - t0) * 0.05)
            suggested.append({
                "name": "zoom_to_range",
                "arguments": {"start_time": t0 - pad, "end_time": t1 + pad},
                "reason": "Focus correlated range",
            })
        if task:
            suggested.append({
                "name": "highlight_task",
                "arguments": {"task_name_or_id": task},
                "reason": "Highlight focus task",
            })
    return {
        "ok": True,
        "message": (
            f"{len(rows)} correlated event(s) for {task or 'scope'}"
            + (" (truncated)" if truncated else "")
        ),
        "task": task,
        "around_time": around_time,
        "window": window,
        "events": rows,
        "correlation": round(score, 2),
        "kinds": sorted(kinds),
        "truncated": truncated,
        "suggested_tools": suggested,
    }


_CRITICAL_PATH_KIND_ORDER: Dict[str, int] = {
    "blocking": 0,
    "sync": 1,
    "priority": 2,
    "execution": 3,
    "migration": 4,
    "search": 5,
}


def build_critical_path(
    events: Sequence[dict],
    *,
    task: str = "",
    timestamp: Optional[float] = None,
    limit: int = 20,
) -> Dict[str, Any]:
    """Turn correlate events into a causal critical-path step list."""
    limit = max(1, min(40, int(limit or 20)))
    rows: List[dict] = []
    for ev in events or []:
        if not isinstance(ev, dict):
            continue
        try:
            t = float(ev.get("time"))
        except (TypeError, ValueError):
            continue
        rows.append({
            "time": t,
            "kind": str(ev.get("kind") or "event"),
            "detail": str(ev.get("detail") or ev.get("note") or ""),
            "task": str(ev.get("task") or task or ""),
            "core": str(ev.get("core") or ""),
            "start": ev.get("start", t),
            "stop": ev.get("stop"),
            "duration": ev.get("duration", ev.get("gap")),
        })
        if rows[-1]["stop"] is None and rows[-1]["duration"] is not None:
            try:
                rows[-1]["stop"] = float(t) + float(rows[-1]["duration"])
            except (TypeError, ValueError):
                pass
    if not rows:
        return {
            "ok": False,
            "message": "No events in scope for critical path",
            "task": task,
            "path": [],
            "confidence": "Low",
            "mermaid": "",
            "graph_nodes": [],
            "blocking_steps": [],
            "preemption_steps": [],
        }
    if timestamp is not None:
        ts = float(timestamp)
        rows.sort(
            key=lambda r: (
                abs(r["time"] - ts),
                _CRITICAL_PATH_KIND_ORDER.get(r["kind"], 9),
                r["time"],
            ),
        )
    else:
        rows.sort(
            key=lambda r: (
                r["time"],
                _CRITICAL_PATH_KIND_ORDER.get(r["kind"], 9),
            ),
        )
    rows = rows[:limit]
    kind_labels = {
        "blocking": "Blocked / off-CPU",
        "sync": "Sync / mutex",
        "priority": "Priority inheritance",
        "execution": "On-CPU execution",
        "migration": "Core migration",
        "search": "Timeline match",
    }
    path: List[Dict[str, Any]] = []
    for i, ev in enumerate(rows, start=1):
        label = kind_labels.get(ev["kind"], ev["kind"])
        detail = ev["detail"]
        start = ev.get("start")
        stop = ev.get("stop")
        try:
            has_interval = (
                start is not None and stop is not None and float(stop) > float(start)
            )
        except (TypeError, ValueError):
            has_interval = False
        if not has_interval:
            start = ev["time"]
            if i < len(rows) and rows[i]["time"] > start:
                stop = rows[i]["time"]
            else:
                stop = start
        path.append({
            "step": i,
            "time": ev["time"],
            "start": start,
            "stop": stop,
            "detail": f"{label}: {detail}" if detail else label,
            "kind": ev["kind"],
            "task": str(ev.get("task") or task or ""),
            "core": str(ev.get("core") or ""),
        })
    kinds = {r["kind"] for r in rows}
    if len(kinds) >= 3 and len(rows) >= 4:
        confidence = "High"
    elif len(rows) >= 2:
        confidence = "Medium"
    else:
        confidence = "Low"
    # Blocking = off-CPU waits; preemption = priority boosts / migrations that
    # reshuffled who ran (best-effort from this task's own event stream).
    blocking_steps = [p for p in path if p["kind"] == "blocking"]
    preemption_steps = [p for p in path if p["kind"] in ("priority", "migration")]
    graph_nodes = [
        {"id": f"S{p['step']}", "label": p["detail"], "kind": p["kind"], "time": p["time"]}
        for p in path
    ]
    mermaid = ""
    if len(graph_nodes) >= 2:
        lines = ["graph LR"]
        for node in graph_nodes:
            safe = str(node["label"]).replace('"', "'")[:80]
            lines.append(f'  {node["id"]}["{safe}"]')
        for a, b in zip(graph_nodes, graph_nodes[1:]):
            lines.append(f'  {a["id"]} --> {b["id"]}')
        mermaid = "\n".join(lines)
    return {
        "ok": True,
        "message": f"{len(path)} step critical path for {task or 'task'}",
        "task": task,
        "timestamp": timestamp,
        "path": path,
        "confidence": confidence,
        "mermaid": mermaid,
        "graph_nodes": graph_nodes,
        "blocking_steps": blocking_steps,
        "preemption_steps": preemption_steps,
    }


def extract_evidence_panel_payload(
    tool_name: str,
    result: Dict[str, Any],
) -> Optional[Dict[str, Any]]:
    """Normalize investigation tool results for the Evidence panel UI."""
    if not isinstance(result, dict) or not result.get("ok"):
        return None
    data = result.get("data") if isinstance(result.get("data"), dict) else {}
    for key in (
        "finding", "hypotheses", "alternatives", "evidence_chain",
        "events", "path", "checks", "confidence", "task", "correlation",
        "root_cause_chain", "historical_knowledge",
    ):
        if key not in data and key in result:
            data[key] = result[key]
    name = str(tool_name or "")
    payload: Dict[str, Any] = {}

    if name == "investigate" or data.get("finding") or data.get("hypotheses"):
        finding = data.get("finding") if isinstance(data.get("finding"), dict) else {}
        payload["conclusion"] = str(finding.get("title") or data.get("conclusion") or "")
        payload["subtitle"] = str(finding.get("text") or "")
        focus_task = str(finding.get("task") or data.get("task") or "").strip()
        ev_items: List[Dict[str, Any]] = []
        for ev in finding.get("evidence") or []:
            item = _normalize_evidence_item(ev, default_task=focus_task)
            if item:
                ev_items.append(item)
        if ev_items:
            payload["evidence"] = ev_items
        if data.get("evidence_chain"):
            payload["evidence_chain"] = str(data.get("evidence_chain") or "")
        payload["alternatives"] = list(data.get("alternatives") or [])
        payload["confidence"] = str(data.get("confidence") or "Medium")
        if data.get("hypotheses"):
            payload["hypotheses"] = list(data.get("hypotheses") or [])
        if data.get("root_cause_chain"):
            payload["root_cause_chain"] = list(data.get("root_cause_chain") or [])
        for extra in (
            "evidence_quality", "evidence_coverage", "evidence_graph",
            "falsification", "investigation_case", "confidence_history",
            "historical_knowledge",
        ):
            if data.get(extra):
                payload[extra] = data[extra]
        if data.get("explanation") and not payload.get("subtitle"):
            payload["subtitle"] = str(data.get("explanation") or "")
    elif name == "find_critical_path" or data.get("path"):
        task = str(data.get("task") or "")
        payload["conclusion"] = f"Critical path: {task}" if task else "Critical path"
        payload["evidence"] = [
            item for item in (
                _normalize_evidence_item(
                    p,
                    default_task=task,
                    label=str(p.get("detail") or ""),
                )
                for p in (data.get("path") or [])
                if isinstance(p, dict)
            )
            if item
        ]
        payload["confidence"] = str(data.get("confidence") or "Medium")
    elif name == "correlate_events" or data.get("events"):
        task = str(data.get("task") or "")
        payload["conclusion"] = f"Correlated events: {task}" if task else "Correlated events"
        payload["evidence"] = [
            item for item in (
                _normalize_evidence_item(
                    e,
                    default_task=task,
                    label=f"{e.get('kind')}: {e.get('detail')}",
                )
                for e in (data.get("events") or [])[:15]
                if isinstance(e, dict)
            )
            if item
        ]
        corr = data.get("correlation")
        payload["confidence"] = (
            f"Correlation {corr}" if corr is not None else "Medium"
        )
    elif name == "search_timeline" or data.get("times") is not None:
        times = []
        for t in (data.get("times") or result.get("times") or []):
            try:
                times.append(float(t))
            except (TypeError, ValueError):
                continue
        query = str(data.get("query") or result.get("query") or "").strip()
        payload["conclusion"] = str(
            result.get("message")
            or data.get("message")
            or (f"{len(times)} timeline hit(s)" if times else "No timeline hits")
        )
        focus_task = str(data.get("task") or "").strip()
        payload["evidence"] = [
            {
                "label": f"timeline: {query}" if query else "timeline hit",
                "time": t if t != int(t) else int(t),
                **({"task": focus_task} if focus_task else {}),
            }
            for t in times[:20]
        ]
        payload["confidence"] = str(data.get("confidence") or "Medium")
    elif name == "detect_priority_inversion" or data.get("inversions") is not None:
        inversions = [
            inv for inv in (data.get("inversions") or []) if isinstance(inv, dict)
        ]
        task = str(data.get("task") or "")
        payload["conclusion"] = str(
            result.get("message")
            or data.get("message")
            or (
                f"{len(inversions)} priority inversion(s)"
                if inversions else "No priority inversion suspects"
            )
        )
        payload["evidence"] = []
        for inv in inversions[:15]:
            pattern = str(inv.get("pattern") or "").strip() or "L/M/H inversion"
            label = "priority: " + pattern
            if inv.get("low"):
                label += f" low={inv.get('low')}"
            if inv.get("medium"):
                label += f" med={inv.get('medium')}"
            if inv.get("high"):
                label += f" high={inv.get('high')}"
            item = _normalize_evidence_item(
                {
                    "label": label,
                    "time": inv.get("time"),
                    "start": inv.get("time"),
                    "stop": (
                        (inv.get("time") or 0) + (inv.get("duration") or 0)
                        if inv.get("time") is not None
                        and inv.get("duration") is not None
                        else inv.get("time")
                    ),
                    "duration": inv.get("duration"),
                    "task": inv.get("task") or task,
                    "core": inv.get("core") or "",
                },
                default_task=task,
            )
            if item:
                payload["evidence"].append(item)
        if inversions:
            payload["evidence_chain"] = (
                f"{len(inversions)} priority-inversion episode(s)"
                + (f" involving {task}" if task else "")
            )
        payload["confidence"] = str(data.get("confidence") or "Medium")
    elif name == "compare_performance" or data.get("checks"):
        primary = data.get("primary")
        if isinstance(primary, dict):
            payload["conclusion"] = str(primary.get("label") or "Performance comparison")
        else:
            payload["conclusion"] = "Performance comparison"
        payload["confidence"] = str(data.get("confidence") or "Medium")
        payload["checks"] = list(data.get("checks") or [])
    elif name == "interpret_query" or data.get("interpreted_question"):
        payload["conclusion"] = str(data.get("interpreted_question") or "")
        scopes = [str(s) for s in (data.get("scope") or []) if s]
        mode = str(data.get("mode") or data.get("kind") or "")
        if scopes:
            payload["subtitle"] = (
                f"{mode}: {', '.join(scopes)}" if mode else ", ".join(scopes)
            )
        elif mode:
            payload["subtitle"] = mode
        payload["confidence"] = "Medium"
        payload["interpreted"] = {
            "interpreted_question": payload["conclusion"],
            "kind": data.get("kind") or mode,
            "mode": mode,
            "scope": scopes,
            "finding_id": str(data.get("finding_id") or ""),
            "task": str(data.get("task") or ""),
        }
    elif name == "validate_experiment" or data.get("result") in (
        "VALIDATED", "PARTIALLY VALIDATED", "DISPROVED", "INCONCLUSIVE",
    ):
        result_label = str(data.get("result") or "INCONCLUSIVE")
        payload["conclusion"] = result_label
        payload["experiment"] = {
            "result": result_label,
            "verdict": format_experiment_verdict(result_label),
            "rows": list(data.get("rows") or []),
        }
        payload["checks"] = [
            {
                "label": str(row.get("metric") or "metric"),
                "status": str(row.get("status") or ""),
                "detail": (
                    f"expected {row.get('expected')} actual {row.get('actual')}"
                ),
            }
            for row in (data.get("rows") or [])
            if isinstance(row, dict)
        ]
        payload["confidence"] = (
            "High" if result_label == "VALIDATED"
            else "Low" if result_label == "DISPROVED"
            else "Medium"
        )
    elif name in (
        "plan_investigation", "suggest_scope", "detect_contradictions",
        "assess_evidence_sufficiency", "cluster_findings", "generate_fingerprint",
        "find_similar_investigations", "regression_localize", "build_causal_chain",
        "generate_experiment_plan", "record_experiment_outcome",
        "score_investigation",
        "analyze_temporal_causality", "build_task_dependency_graph",
        "decompose_response_time", "rank_root_causes", "verify_claim",
        "challenge_conclusion", "investigation_memory", "cluster_incidents",
        "close_investigation", "analyze_distribution", "analyze_periodicity",
        "summarize_investigation_context",
    ) or data.get("steps") or data.get("verdict") or data.get("pattern"):
        payload["conclusion"] = str(result.get("message") or data.get("message") or name)
        payload["confidence"] = str(data.get("confidence") or "Medium")
        if data.get("mermaid"):
            payload["evidence_chain"] = str(data.get("mermaid"))

    if not (
        payload.get("conclusion")
        or payload.get("evidence")
        or payload.get("evidence_chain")
        or payload.get("alternatives")
        or payload.get("checks")
    ):
        return None
    score_data = compute_evidence_score(
        payload.get("evidence"),
        alternatives=payload.get("alternatives"),
        evidence_chain=payload.get("evidence_chain"),
        checks=payload.get("checks"),
    )
    payload["evidence_score"] = score_data["score"]
    payload["evidence_score_breakdown"] = score_data["breakdown"]
    payload["evidence_score_bar"] = score_data["bar"]
    quality = compute_evidence_quality(
        score=score_data["score"],
        breakdown=score_data.get("breakdown"),
        evidence=payload.get("evidence"),
        alternatives=payload.get("alternatives"),
        checks=payload.get("checks"),
        evidence_chain=str(payload.get("evidence_chain") or ""),
    )
    payload["evidence_quality"] = quality
    payload["evidence_quality_bar"] = quality.get("bar")
    finding = data.get("finding") if isinstance(data.get("finding"), dict) else None
    if finding is None and payload.get("conclusion"):
        finding = {
            "title": payload.get("conclusion"),
            "text": payload.get("subtitle") or "",
            "evidence": payload.get("evidence") or [],
        }
    case = build_investigation_case(
        {
            "finding": finding or {},
            "hypotheses": payload.get("hypotheses") or [],
            "alternatives": payload.get("alternatives") or [],
            "evidence": payload.get("evidence") or [],
            "root_cause_chain": payload.get("root_cause_chain") or [],
            "plan": data.get("plan"),
            "suggested_tools": data.get("suggested_tools") or [],
            "checks": payload.get("checks") or [],
            "evidence_score": score_data["score"],
            "evidence_score_breakdown": score_data.get("breakdown"),
            "evidence_chain": payload.get("evidence_chain") or "",
            "message": payload.get("conclusion") or "",
        },
        score_data=score_data,
        tools_run=data.get("suggested_tools") or data.get("tools_executed"),
    )
    payload["investigation_case"] = case
    payload["coverage"] = case.get("evidence_coverage") or case.get("coverage")
    payload["falsify"] = case.get("falsification") or case.get("falsify")
    graph = case.get("evidence_graph") or {}
    payload["graph_mermaid"] = (
        case.get("graph_mermaid")
        or evidence_graph_mermaid(graph.get("nodes"), graph.get("edges"))
    )
    payload["hypotheses_managed"] = case.get("hypotheses")
    payload["tool_reasons"] = case.get("tool_reasons") or []
    payload["confidence_evolution"] = format_confidence_evolution(
        case.get("confidence_history"))
    hk = data.get("historical_knowledge") or payload.get("historical_knowledge")
    if hk:
        payload["historical_knowledge"] = hk
    return payload


def _evidence_items_have_times(evidence: Any) -> bool:
    """True when any evidence dict carries a concrete ``time`` (jump:TIME)."""
    if not isinstance(evidence, (list, tuple)):
        return False
    return any(
        isinstance(e, dict) and e.get("time") is not None
        for e in evidence
    )


def refresh_evidence_panel_scores(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Recompute heuristic score / quality fields on an Evidence panel payload."""
    out = dict(payload or {})
    score_data = compute_evidence_score(
        out.get("evidence"),
        alternatives=out.get("alternatives"),
        evidence_chain=str(out.get("evidence_chain") or ""),
        checks=out.get("checks"),
    )
    out["evidence_score"] = score_data["score"]
    out["evidence_score_breakdown"] = score_data["breakdown"]
    out["evidence_score_bar"] = score_data["bar"]
    quality = compute_evidence_quality(
        score=score_data["score"],
        breakdown=score_data.get("breakdown"),
        evidence=out.get("evidence"),
        alternatives=out.get("alternatives"),
        checks=out.get("checks"),
        evidence_chain=str(out.get("evidence_chain") or ""),
    )
    out["evidence_quality"] = quality
    out["evidence_quality_bar"] = quality.get("bar")
    return out


def merge_evidence_panel_payload(
    prev: Optional[Dict[str, Any]],
    new: Optional[Dict[str, Any]],
) -> Optional[Dict[str, Any]]:
    """Carry forward timed evidence when a later tool omits it.

    ``auto_investigate`` ends with planner tools (``rank_root_causes``,
    ``challenge_conclusion``, ``score_investigation``, …) that publish a
    conclusion but no ``jump:TIME`` rows. Without a merge, replacing the
    Evidence panel collapses the heuristic score to 0% even though earlier
    ``investigate`` / ``correlate_events`` / ``find_critical_path`` results
    were strong.
    """
    if not isinstance(new, dict) or not new:
        return dict(prev) if isinstance(prev, dict) and prev else new
    if not isinstance(prev, dict) or not prev:
        return dict(new)
    out = dict(new)
    if not _evidence_items_have_times(out.get("evidence")) and _evidence_items_have_times(
        prev.get("evidence")
    ):
        out["evidence"] = list(prev.get("evidence") or [])
    if not str(out.get("evidence_chain") or "").strip() and str(
        prev.get("evidence_chain") or ""
    ).strip():
        out["evidence_chain"] = prev.get("evidence_chain")
    if not out.get("checks") and prev.get("checks"):
        out["checks"] = list(prev.get("checks") or [])
    for key in (
        "alternatives",
        "hypotheses",
        "hypotheses_managed",
        "root_cause_chain",
        "finding",
        "subtitle",
    ):
        if not out.get(key) and prev.get(key):
            out[key] = prev[key]
    return refresh_evidence_panel_scores(out)


def _evidence_jump_token(value: Any) -> str:
    try:
        tn = float(value)
        return str(int(tn)) if tn.is_integer() else str(tn)
    except (TypeError, ValueError):
        return str(value or "")


_BTF_HYP_HREF_RE = re.compile(
    r"btfhyp:(?://)?([a-z_]+)/([^?\s#]*)",
    re.IGNORECASE,
)


def btf_hyp_href(action: str, hyp_id: str = "") -> str:
    """Clickable Evidence-panel action (Support / Reject / Test / Compare)."""
    act = re.sub(r"[^a-z_]", "", str(action or "").lower()) or "test"
    hid = re.sub(r"[^A-Za-z0-9_.-]", "", str(hyp_id or "all")) or "all"
    return f"btfhyp:{act}/{hid}"


def parse_btf_hyp_href(href: Any) -> Tuple[str, str]:
    """Parse ``btfhyp:supported/h1`` → ``(action, hypothesis_id)``."""
    m = _BTF_HYP_HREF_RE.search(str(href or ""))
    if not m:
        return "", ""
    return m.group(1).lower(), (m.group(2) or "all")


def format_hypothesis_action_links(hyp_id: str, labels: Dict[str, str]) -> str:
    hid = str(hyp_id or "h1")
    parts = []
    for action, key, fallback in (
        ("supported", "support_action", "Support"),
        ("rejected", "reject_action", "Reject"),
        ("need_evidence", "need_evidence_action", "Need evidence"),
        ("test", "test_action", "Test"),
    ):
        parts.append(f"[{labels.get(key, fallback)}]({btf_hyp_href(action, hid)})")
    return " · ".join(parts)


_BTF_SCOPE_HREF_RE = re.compile(
    r"btfscope:(?://)?([a-z_]+)/([^?\s#]*)",
    re.IGNORECASE,
)
_BTF_EXP_HREF_RE = re.compile(
    r"btfexp:(?://)?([a-z_]+)/([^?\s#]*)",
    re.IGNORECASE,
)
_BTF_TOOL_HREF_RE = re.compile(
    r"btftool:(?://)?([a-z_]+)/([^?\s#]*)",
    re.IGNORECASE,
)


def btf_scope_href(action: str, key: str = "") -> str:
    act = re.sub(r"[^a-z_]", "", str(action or "").lower()) or "run"
    kid = re.sub(r"[^A-Za-z0-9_. -]", "", str(key or "all")).strip() or "all"
    kid = kid.replace(" ", "_")
    return f"btfscope:{act}/{kid}"


def parse_btf_scope_href(href: Any) -> Tuple[str, str]:
    m = _BTF_SCOPE_HREF_RE.search(str(href or ""))
    if not m:
        return "", ""
    key = (m.group(2) or "all").replace("_", " ")
    return m.group(1).lower(), key


def format_scope_action_links(
    interpreted: Optional[dict],
    labels: Optional[Dict[str, str]] = None,
) -> str:
    """Markdown for interpret_query: scope toggles + Run / Edit."""
    lab = labels if isinstance(labels, dict) else {}
    data = interpreted if isinstance(interpreted, dict) else {}
    scopes = [str(s) for s in (data.get("scope") or []) if s]
    options = list(INVESTIGATION_SCOPE_OPTIONS)
    for s in scopes:
        if s not in options:
            options.append(s)
    lines: List[str] = []
    question = str(data.get("interpreted_question") or "").strip()
    if question:
        lines.append(f"**{lab.get('interpreted', 'Interpreted question')}:** {question}")
    lines.append("")
    lines.append(f"**{lab.get('scope', 'Investigation scope')}**")
    on_lab = lab.get("scope_on", "on")
    off_lab = lab.get("scope_off", "off")
    for opt in options:
        active = opt in scopes
        mark = "✓" if active else "○"
        lines.append(
            f"- {mark} {opt} "
            f"[{on_lab if not active else off_lab}]({btf_scope_href('toggle', opt)})"
        )
    lines.append("")
    lines.append(
        f"[{lab.get('run_investigation', 'Run investigation')}]({btf_scope_href('run', 'all')}) "
        f"[{lab.get('edit_scope', 'Edit scope')}]({btf_scope_href('edit', 'all')})"
    )
    return "\n".join(lines)


def btf_exp_href(action: str, key: str = "all") -> str:
    act = re.sub(r"[^a-z_]", "", str(action or "").lower()) or "save"
    kid = re.sub(r"[^A-Za-z0-9_.-]", "", str(key or "all")) or "all"
    return f"btfexp:{act}/{kid}"


def parse_btf_exp_href(href: Any) -> Tuple[str, str]:
    m = _BTF_EXP_HREF_RE.search(str(href or ""))
    if not m:
        return "", ""
    return m.group(1).lower(), (m.group(2) or "all")


def btf_tool_href(action: str, name: str = "") -> str:
    act = re.sub(r"[^a-z_]", "", str(action or "").lower()) or "why"
    kid = re.sub(r"[^A-Za-z0-9_.-]", "", str(name or "tool")) or "tool"
    return f"btftool:{act}/{kid}"


def parse_btf_tool_href(href: Any) -> Tuple[str, str]:
    m = _BTF_TOOL_HREF_RE.search(str(href or ""))
    if not m:
        return "", ""
    return m.group(1).lower(), (m.group(2) or "")


# UI strings for Evidence & Validation and plan status. Keep in sync with
# web/src/utils/aiInvestigation.js EVIDENCE_PANEL_LABELS.
EVIDENCE_PANEL_LABELS: Dict[str, Dict[str, str]] = {
    "English": {
        "role": "Evidence & Validation",
        "evidence": "Evidence",
        "evidence_chain": "Evidence chain",
        "confidence": "Confidence",
        "score": "AI Evidence Score — heuristic",
        "alternatives": "Alternative hypotheses",
        "checklist": "Verification checklist",
        "tree": "Investigation tree",
        "investigation": "Investigation",
        "done": "done",
        "critical_path": "Critical path",
        "correlated_events": "Correlated events",
        "performance_comparison": "Performance comparison",
        "correlation": "Correlation",
        "item": "item",
        "check": "check",
        "high": "High",
        "medium": "Medium",
        "low": "Low",
        "untested": "untested",
        "confirmed": "confirmed",
        "rejected": "rejected",
        "plausible": "plausible",
    },
    "Traditional Chinese (繁體中文)": {
        "role": "證據與驗證",
        "evidence": "證據",
        "evidence_chain": "證據鏈",
        "confidence": "置信度",
        "score": "AI 證據評分 — 啟發式",
        "alternatives": "替代假設",
        "checklist": "驗證清單",
        "tree": "調查樹",
        "investigation": "調查",
        "done": "完成",
        "critical_path": "關鍵路徑",
        "correlated_events": "相關事件",
        "performance_comparison": "性能對比",
        "correlation": "相關性",
        "item": "項目",
        "check": "檢查",
        "high": "高",
        "medium": "中",
        "low": "低",
        "untested": "未驗證",
        "confirmed": "已確認",
        "rejected": "已排除",
        "plausible": "可能",
    },
    "Simplified Chinese (简体中文)": {
        "role": "证据与验证",
        "evidence": "证据",
        "evidence_chain": "证据链",
        "confidence": "置信度",
        "score": "AI 证据评分 — 启发式",
        "alternatives": "替代假设",
        "checklist": "验证清单",
        "tree": "调查树",
        "investigation": "调查",
        "done": "完成",
        "critical_path": "关键路径",
        "correlated_events": "相关事件",
        "performance_comparison": "性能对比",
        "correlation": "相关性",
        "item": "项目",
        "check": "检查",
        "high": "高",
        "medium": "中",
        "low": "低",
        "untested": "未验证",
        "confirmed": "已确认",
        "rejected": "已排除",
        "plausible": "可能",
    },
    "Japanese (日本語)": {
        "role": "根拠と検証",
        "evidence": "根拠",
        "evidence_chain": "根拠チェーン",
        "confidence": "信頼度",
        "score": "AI 根拠スコア — ヒューリスティック",
        "alternatives": "代替仮説",
        "checklist": "検証チェックリスト",
        "tree": "調査ツリー",
        "investigation": "調査",
        "done": "完了",
        "critical_path": "クリティカルパス",
        "correlated_events": "相関イベント",
        "performance_comparison": "性能比較",
        "correlation": "相関",
        "item": "項目",
        "check": "チェック",
        "high": "高",
        "medium": "中",
        "low": "低",
        "untested": "未検証",
        "confirmed": "確認済み",
        "rejected": "却下",
        "plausible": "妥当",
    },
    "Korean (한국어)": {
        "role": "증거 및 검증",
        "evidence": "증거",
        "evidence_chain": "증거 체인",
        "confidence": "신뢰도",
        "score": "AI 증거 점수 — 휴리스틱",
        "alternatives": "대안 가설",
        "checklist": "검증 체크리스트",
        "tree": "조사 트리",
        "investigation": "조사",
        "done": "완료",
        "critical_path": "크리티컬 패스",
        "correlated_events": "상관 이벤트",
        "performance_comparison": "성능 비교",
        "correlation": "상관",
        "item": "항목",
        "check": "검사",
        "high": "높음",
        "medium": "중간",
        "low": "낮음",
        "untested": "미검증",
        "confirmed": "확인됨",
        "rejected": "기각",
        "plausible": "가능",
    },
    "German": {
        "role": "Belege & Validierung",
        "evidence": "Belege",
        "evidence_chain": "Belegkette",
        "confidence": "Vertrauen",
        "score": "AI-Belegscore — heuristisch",
        "alternatives": "Alternative Hypothesen",
        "checklist": "Prüfliste",
        "tree": "Untersuchungsbaum",
        "investigation": "Untersuchung",
        "done": "fertig",
        "critical_path": "Kritischer Pfad",
        "correlated_events": "Korrelierte Ereignisse",
        "performance_comparison": "Leistungsvergleich",
        "correlation": "Korrelation",
        "item": "Eintrag",
        "check": "Prüfung",
        "high": "Hoch",
        "medium": "Mittel",
        "low": "Niedrig",
        "untested": "ungeprüft",
        "confirmed": "bestätigt",
        "rejected": "abgelehnt",
        "plausible": "plausibel",
    },
    "French": {
        "role": "Preuves et validation",
        "evidence": "Preuves",
        "evidence_chain": "Chaîne de preuves",
        "confidence": "Confiance",
        "score": "Score de preuve IA — heuristique",
        "alternatives": "Hypothèses alternatives",
        "checklist": "Liste de vérification",
        "tree": "Arbre d'investigation",
        "investigation": "Investigation",
        "done": "terminé",
        "critical_path": "Chemin critique",
        "correlated_events": "Événements corrélés",
        "performance_comparison": "Comparaison de performance",
        "correlation": "Corrélation",
        "item": "élément",
        "check": "contrôle",
        "high": "Élevée",
        "medium": "Moyenne",
        "low": "Faible",
        "untested": "non testé",
        "confirmed": "confirmé",
        "rejected": "rejeté",
        "plausible": "plausible",
    },
    "Spanish": {
        "role": "Evidencia y validación",
        "evidence": "Evidencia",
        "evidence_chain": "Cadena de evidencia",
        "confidence": "Confianza",
        "score": "Puntuación de evidencia IA — heurística",
        "alternatives": "Hipótesis alternativas",
        "checklist": "Lista de verificación",
        "tree": "Árbol de investigación",
        "investigation": "Investigación",
        "done": "hecho",
        "critical_path": "Ruta crítica",
        "correlated_events": "Eventos correlacionados",
        "performance_comparison": "Comparación de rendimiento",
        "correlation": "Correlación",
        "item": "elemento",
        "check": "comprobación",
        "high": "Alta",
        "medium": "Media",
        "low": "Baja",
        "untested": "sin probar",
        "confirmed": "confirmado",
        "rejected": "rechazado",
        "plausible": "plausible",
    },
}


_EVIDENCE_PANEL_EXTRA: Dict[str, Dict[str, str]] = {
    "English": {
        "quality": "Evidence Quality",
        "coverage": "Evidence Coverage",
        "finding": "Finding",
        "direct_evidence": "Direct evidence",
        "interpretation": "Interpretation",
        "checks": "Checks",
        "missing_evidence": "Missing evidence",
        "next_action": "Next action",
        "investigation_details": "Investigation details",
        "status": "Status",
        "status_confirmed": "Confirmed",
        "status_correlated": "Correlated",
        "status_suspected": "Suspected",
        "status_not_observed": "Not observed",
        "status_insufficient": "Insufficient data",
        "col_time": "Time",
        "col_event": "Observed event",
        "col_task": "Task",
        "col_core": "Core",
        "col_duration": "Duration",
        "check_header": "Check",
        "observed": "Observed",
        "not_observed": "Not observed",
        "not_evaluated": "Not evaluated",
        "insufficient_evidence": "Insufficient evidence",
        "disprove": "What would disprove this",
        "graph": "Evidence graph",
        "supported": "supported",
        "possible": "possible",
        "needs_evidence": "needs evidence",
        "need_evidence": "needs evidence",
        "unverified": "unverified claims",
        "next_check": "Recommended next check",
        "supporting": "Supporting evidence",
        "contradicting": "Contradicting",
        "timeline_evidence": "Timeline evidence",
        "tools_used": "Tools used",
        "rows_label": "rows",
        "cost": "Investigation cost",
        "claims": "Claims",
        "validation": "Validation",
        "evolution": "Confidence evolution",
        "privacy": "Privacy",
        "expand_all": "Expand all",
        "collapse_all": "Collapse all",
        "historical": "Historical knowledge",
        "previous_issue": "Previous issue",
        "known_fix": "Known fix",
        "last_occurrence": "Last occurrence",
        "support_action": "Support",
        "reject_action": "Reject",
        "need_evidence_action": "Need evidence",
        "test_action": "Test",
        "compare_action": "Compare hypotheses",
        "interpreted": "Interpreted question",
        "scope": "Investigation scope",
        "run_investigation": "Run investigation",
        "edit_scope": "Edit scope",
        "experiment_result": "Experiment result",
        "hypothesis_validated": "Hypothesis validated",
        "hypothesis_disproved": "Hypothesis disproved",
        "hypothesis_partial": "Hypothesis partially validated",
        "save_knowledge": "Save to knowledge",
        "scope_on": "on",
        "scope_off": "off",
        "quality_direct": "Direct evidence",
        "quality_timeline": "Timeline correlation",
        "quality_metric": "Metric correlation",
        "quality_alternative": "Alternative tested",
        "coverage_observed": "Directly observed",
        "coverage_timeline": "Timeline verified",
        "coverage_metric": "Metric verified",
        "coverage_unverified": "Unverified assumptions",
        "why_action": "Why?",
        "typical_rate": "Typical rate",
        "current_rate": "Current",
    },
    "Traditional Chinese (繁體中文)": {
        "quality": "證據品質",
        "coverage": "證據覆蓋",
        "disprove": "如何推翻此結論",
        "graph": "證據圖",
        "supported": "已支持",
        "possible": "可能",
        "needs_evidence": "需要證據",
        "unverified": "未驗證的主張",
        "next_check": "建議下一步",
        "supporting": "支持證據",
        "contradicting": "矛盾證據",
        "timeline_evidence": "時間軸證據",
        "tools_used": "已用工具",
        "rows_label": "列",
        "investigation_details": "調查詳情",
        "cost": "調查成本",
        "claims": "主張",
        "validation": "驗證",
        "evolution": "置信度演進",
        "privacy": "隱私",
        "historical": "歷史知識",
        "previous_issue": "先前問題",
        "known_fix": "已知修復",
        "last_occurrence": "上次出現",
        "support_action": "支持",
        "reject_action": "排除",
        "need_evidence_action": "需要證據",
        "test_action": "驗證",
        "compare_action": "比較假設",
        "interpreted": "解讀後的問題",
        "scope": "調查範圍",
        "run_investigation": "開始調查",
        "edit_scope": "編輯範圍",
        "experiment_result": "實驗結果",
        "hypothesis_validated": "假設已成立",
        "hypothesis_disproved": "假設已排除",
        "hypothesis_partial": "假設部分成立",
        "save_knowledge": "存入知識庫",
        "scope_on": "開",
        "scope_off": "關",
        "quality_direct": "直接證據",
        "quality_timeline": "時間軸相關",
        "quality_metric": "指標相關",
        "quality_alternative": "已測替代假設",
        "coverage_observed": "直接觀察",
        "coverage_timeline": "時間軸已驗證",
        "coverage_metric": "指標已驗證",
        "coverage_unverified": "未驗證假設",
        "why_action": "為何？",
        "typical_rate": "典型速率",
        "current_rate": "目前",
        "expand_all": "全部展開",
        "collapse_all": "全部摺疊",
    },
    "Simplified Chinese (简体中文)": {
        "quality": "证据品质",
        "coverage": "证据覆盖",
        "disprove": "如何推翻此结论",
        "graph": "证据图",
        "supported": "已支持",
        "possible": "可能",
        "needs_evidence": "需要证据",
        "unverified": "未验证的主张",
        "next_check": "建议下一步",
        "supporting": "支持证据",
        "investigation_details": "调查详情",
        "cost": "调查成本",
        "claims": "主张",
        "validation": "验证",
        "evolution": "置信度演进",
        "privacy": "隐私",
        "historical": "历史知识",
        "previous_issue": "先前问题",
        "known_fix": "已知修复",
        "last_occurrence": "上次出现",
        "support_action": "支持",
        "reject_action": "排除",
        "need_evidence_action": "需要证据",
        "test_action": "验证",
        "compare_action": "比较假设",
        "interpreted": "解读后的问题",
        "scope": "调查范围",
        "run_investigation": "开始调查",
        "edit_scope": "编辑范围",
        "experiment_result": "实验结果",
        "hypothesis_validated": "假设已成立",
        "hypothesis_disproved": "假设已排除",
        "hypothesis_partial": "假设部分成立",
        "save_knowledge": "存入知识库",
        "scope_on": "开",
        "scope_off": "关",
        "quality_direct": "直接证据",
        "quality_timeline": "时间轴相关",
        "quality_metric": "指标相关",
        "quality_alternative": "已测替代假设",
        "coverage_observed": "直接观察",
        "coverage_timeline": "时间轴已验证",
        "coverage_metric": "指标已验证",
        "coverage_unverified": "未验证假设",
        "why_action": "为何？",
        "typical_rate": "典型速率",
        "current_rate": "当前",
        "expand_all": "全部展开",
        "collapse_all": "全部折叠",
    },
    "Japanese (日本語)": {
        "quality": "根拠の質",
        "coverage": "根拠カバレッジ",
        "disprove": "反証になるもの",
        "graph": "根拠グラフ",
        "supported": "支持",
        "possible": "可能性あり",
        "needs_evidence": "根拠不足",
        "unverified": "未検証の主張",
        "next_check": "次の確認",
        "supporting": "支持する根拠",
        "investigation_details": "調査詳細",
        "cost": "調査コスト",
        "claims": "主張",
        "validation": "検証",
        "evolution": "信頼度の推移",
        "privacy": "プライバシー",
        "historical": "過去の知見",
        "previous_issue": "過去の問題",
        "known_fix": "既知の対策",
        "last_occurrence": "前回の発生",
        "support_action": "支持",
        "reject_action": "却下",
        "need_evidence_action": "根拠不足",
        "test_action": "検証",
        "compare_action": "仮説を比較",
        "interpreted": "解釈した質問",
        "scope": "調査範囲",
        "run_investigation": "調査を実行",
        "edit_scope": "範囲を編集",
        "experiment_result": "実験結果",
        "hypothesis_validated": "仮説は妥当",
        "hypothesis_disproved": "仮説は否定",
        "hypothesis_partial": "仮説は部分的に妥当",
        "save_knowledge": "知見に保存",
        "scope_on": "オン",
        "scope_off": "オフ",
        "quality_direct": "直接根拠",
        "quality_timeline": "タイムライン相関",
        "quality_metric": "指標相関",
        "quality_alternative": "代替仮説を検証",
        "coverage_observed": "直接観測",
        "coverage_timeline": "タイムライン検証",
        "coverage_metric": "指標検証",
        "coverage_unverified": "未検証の仮定",
        "why_action": "理由",
        "typical_rate": "典型値",
        "current_rate": "現在",
        "expand_all": "すべて展開",
        "collapse_all": "すべて折りたたむ",
    },
    "Korean (한국어)": {
        "quality": "증거 품질",
        "coverage": "증거 커버리지",
        "disprove": "이 결론을 뒤집는 증거",
        "graph": "증거 그래프",
        "supported": "지지됨",
        "possible": "가능",
        "needs_evidence": "증거 필요",
        "unverified": "미검증 주장",
        "next_check": "다음 확인",
        "supporting": "지지 증거",
        "investigation_details": "조사 세부",
        "cost": "조사 비용",
        "claims": "주장",
        "validation": "검증",
        "evolution": "신뢰도 변화",
        "privacy": "개인정보",
        "historical": "과거 지식",
        "previous_issue": "이전 이슈",
        "known_fix": "알려진 수정",
        "last_occurrence": "최근 발생",
        "support_action": "지지",
        "reject_action": "기각",
        "need_evidence_action": "증거 필요",
        "test_action": "검증",
        "compare_action": "가설 비교",
        "interpreted": "해석된 질문",
        "scope": "조사 범위",
        "run_investigation": "조사 실행",
        "edit_scope": "범위 편집",
        "experiment_result": "실험 결과",
        "hypothesis_validated": "가설 타당",
        "hypothesis_disproved": "가설 기각",
        "hypothesis_partial": "가설 부분 타당",
        "save_knowledge": "지식에 저장",
        "scope_on": "켜짐",
        "scope_off": "꺼짐",
        "quality_direct": "직접 증거",
        "quality_timeline": "타임라인 상관",
        "quality_metric": "메트릭 상관",
        "quality_alternative": "대안 검증",
        "coverage_observed": "직접 관측",
        "coverage_timeline": "타임라인 검증",
        "coverage_metric": "메트릭 검증",
        "coverage_unverified": "미검증 가정",
        "why_action": "이유",
        "typical_rate": "전형 비율",
        "current_rate": "현재",
        "expand_all": "모두 펼치기",
        "collapse_all": "모두 접기",
    },
    "German": {
        "quality": "Belegqualität",
        "coverage": "Belegabdeckung",
        "disprove": "Was würde das widerlegen",
        "graph": "Beleggraph",
        "supported": "gestützt",
        "possible": "möglich",
        "needs_evidence": "Belege nötig",
        "unverified": "unbestätigte Aussagen",
        "next_check": "Nächster Prüfpunkt",
        "supporting": "Stützende Belege",
        "investigation_details": "Untersuchungsdetails",
        "cost": "Untersuchungskosten",
        "claims": "Aussagen",
        "validation": "Validierung",
        "evolution": "Konfidenzverlauf",
        "privacy": "Datenschutz",
        "historical": "Historisches Wissen",
        "previous_issue": "Früheres Problem",
        "known_fix": "Bekannte Lösung",
        "last_occurrence": "Letztes Auftreten",
        "support_action": "Stützen",
        "reject_action": "Ablehnen",
        "need_evidence_action": "Belege nötig",
        "test_action": "Prüfen",
        "compare_action": "Hypothesen vergleichen",
        "interpreted": "Interpretierte Frage",
        "scope": "Untersuchungsbereich",
        "run_investigation": "Untersuchung starten",
        "edit_scope": "Bereich bearbeiten",
        "experiment_result": "Experimentergebnis",
        "hypothesis_validated": "Hypothese bestätigt",
        "hypothesis_disproved": "Hypothese widerlegt",
        "hypothesis_partial": "Hypothese teilweise bestätigt",
        "save_knowledge": "Im Wissen speichern",
        "scope_on": "an",
        "scope_off": "aus",
        "quality_direct": "Direkte Belege",
        "quality_timeline": "Zeitlinienkorrelation",
        "quality_metric": "Metrikkorrelation",
        "quality_alternative": "Alternative geprüft",
        "coverage_observed": "Direkt beobachtet",
        "coverage_timeline": "Zeitlinie geprüft",
        "coverage_metric": "Metrik geprüft",
        "coverage_unverified": "Ungeprüfte Annahmen",
        "why_action": "Warum?",
        "typical_rate": "Typische Rate",
        "current_rate": "Aktuell",
        "expand_all": "Alle aufklappen",
        "collapse_all": "Alle einklappen",
    },
    "French": {
        "quality": "Qualité des preuves",
        "coverage": "Couverture des preuves",
        "disprove": "Ce qui infirmerait ceci",
        "graph": "Graphe de preuves",
        "supported": "étayé",
        "possible": "possible",
        "needs_evidence": "preuves nécessaires",
        "unverified": "affirmations non vérifiées",
        "next_check": "Prochaine vérification",
        "supporting": "Preuves à l'appui",
        "investigation_details": "Détails de l'investigation",
        "cost": "Coût d'investigation",
        "claims": "Affirmations",
        "validation": "Validation",
        "evolution": "Évolution de la confiance",
        "privacy": "Confidentialité",
        "historical": "Connaissances historiques",
        "previous_issue": "Problème antérieur",
        "known_fix": "Correctif connu",
        "last_occurrence": "Dernière occurrence",
        "support_action": "Étayer",
        "reject_action": "Rejeter",
        "need_evidence_action": "Preuves nécessaires",
        "test_action": "Tester",
        "compare_action": "Comparer les hypothèses",
        "interpreted": "Question interprétée",
        "scope": "Périmètre d'investigation",
        "run_investigation": "Lancer l'investigation",
        "edit_scope": "Modifier le périmètre",
        "experiment_result": "Résultat d'expérience",
        "hypothesis_validated": "Hypothèse validée",
        "hypothesis_disproved": "Hypothèse infirmée",
        "hypothesis_partial": "Hypothèse partiellement validée",
        "save_knowledge": "Enregistrer dans les connaissances",
        "scope_on": "oui",
        "scope_off": "non",
        "quality_direct": "Preuve directe",
        "quality_timeline": "Corrélation temporelle",
        "quality_metric": "Corrélation métrique",
        "quality_alternative": "Alternative testée",
        "coverage_observed": "Directement observé",
        "coverage_timeline": "Chronologie vérifiée",
        "coverage_metric": "Métrique vérifiée",
        "coverage_unverified": "Hypothèses non vérifiées",
        "why_action": "Pourquoi ?",
        "typical_rate": "Taux typique",
        "current_rate": "Actuel",
        "expand_all": "Tout développer",
        "collapse_all": "Tout réduire",
    },
    "Spanish": {
        "quality": "Calidad de evidencia",
        "coverage": "Cobertura de evidencia",
        "disprove": "Qué refutaría esto",
        "graph": "Grafo de evidencia",
        "supported": "respaldado",
        "possible": "posible",
        "needs_evidence": "falta evidencia",
        "unverified": "afirmaciones no verificadas",
        "next_check": "Siguiente comprobación",
        "supporting": "Evidencia de apoyo",
        "investigation_details": "Detalles de la investigación",
        "cost": "Coste de investigación",
        "claims": "Afirmaciones",
        "validation": "Validación",
        "evolution": "Evolución de la confianza",
        "privacy": "Privacidad",
        "historical": "Conocimiento histórico",
        "previous_issue": "Incidencia previa",
        "known_fix": "Corrección conocida",
        "last_occurrence": "Última aparición",
        "support_action": "Respaldar",
        "reject_action": "Rechazar",
        "need_evidence_action": "Falta evidencia",
        "test_action": "Probar",
        "compare_action": "Comparar hipótesis",
        "interpreted": "Pregunta interpretada",
        "scope": "Alcance de investigación",
        "run_investigation": "Ejecutar investigación",
        "edit_scope": "Editar alcance",
        "experiment_result": "Resultado del experimento",
        "hypothesis_validated": "Hipótesis validada",
        "hypothesis_disproved": "Hipótesis refutada",
        "hypothesis_partial": "Hipótesis parcialmente validada",
        "save_knowledge": "Guardar en conocimiento",
        "scope_on": "sí",
        "scope_off": "no",
        "quality_direct": "Evidencia directa",
        "quality_timeline": "Correlación temporal",
        "quality_metric": "Correlación métrica",
        "quality_alternative": "Alternativa comprobada",
        "coverage_observed": "Observado directamente",
        "coverage_timeline": "Línea de tiempo verificada",
        "coverage_metric": "Métrica verificada",
        "coverage_unverified": "Supuestos no verificados",
        "why_action": "¿Por qué?",
        "typical_rate": "Tasa típica",
        "current_rate": "Actual",
        "expand_all": "Expandir todo",
        "collapse_all": "Contraer todo",
    },
}
for _lang, _extra in _EVIDENCE_PANEL_EXTRA.items():
    _extra.setdefault("need_evidence", _extra.get("needs_evidence", "needs evidence"))
    EVIDENCE_PANEL_LABELS[_lang].update(_extra)


def normalize_response_language(lang: str) -> str:
    """Map a reply-language setting to an EVIDENCE_PANEL_LABELS key."""
    want = (lang or "").strip()
    if want in EVIDENCE_PANEL_LABELS:
        return want
    low = want.lower()
    for key in EVIDENCE_PANEL_LABELS:
        if key.lower() == low or key.lower() in low or low in key.lower():
            return key
    if "简体" in want or "simplified" in low:
        return "Simplified Chinese (简体中文)"
    if "繁體" in want or "繁体" in want or "traditional" in low:
        return "Traditional Chinese (繁體中文)"
    if "日本" in want or "japanese" in low:
        return "Japanese (日本語)"
    if "한국" in want or "korean" in low:
        return "Korean (한국어)"
    return "English"


def evidence_panel_labels(response_language: str = "English") -> Dict[str, str]:
    key = normalize_response_language(response_language)
    return dict(EVIDENCE_PANEL_LABELS[key])


_EVIDENCE_STATUS_KEYS: Tuple[str, ...] = (
    "high", "medium", "low", "untested", "confirmed", "rejected", "plausible",
    "supported", "possible", "needs_evidence", "need_evidence",
)
_EVIDENCE_PREFIX_KEYS: Tuple[str, ...] = (
    "critical_path", "correlated_events", "performance_comparison",
)


def _canonical_evidence_status(text: str) -> Optional[str]:
    """Map an English or already-localized status token back to its key."""
    t = str(text or "").strip()
    if not t:
        return None
    low = t.lower()
    for key in _EVIDENCE_STATUS_KEYS:
        if low == key:
            return key
    for lang_labels in EVIDENCE_PANEL_LABELS.values():
        for key in _EVIDENCE_STATUS_KEYS:
            if t == lang_labels.get(key):
                return key
    return None


def _localize_evidence_token(text: str, labels: Dict[str, str]) -> str:
    t = str(text or "").strip()
    if not t:
        return t
    canon = _canonical_evidence_status(t)
    if canon:
        return labels[canon]
    # Correlation N — accept English or any localized "Correlation" prefix.
    for lang_labels in EVIDENCE_PANEL_LABELS.values():
        corr = str(lang_labels.get("correlation") or "").strip()
        if corr and (t.startswith(corr + " ") or t == corr):
            rest = t[len(corr):].strip()
            return f"{labels['correlation']} {rest}".strip()
    if t.startswith("Correlation "):
        return f"{labels['correlation']} {t[12:].strip()}"
    english_prefixes = {
        "critical_path": ("Critical path:", "Critical path"),
        "correlated_events": ("Correlated events:", "Correlated events"),
        "performance_comparison": (
            "Performance comparison:", "Performance comparison",
        ),
    }
    for lk in _EVIDENCE_PREFIX_KEYS:
        candidates = list(english_prefixes.get(lk, ()))
        for lang_labels in EVIDENCE_PANEL_LABELS.values():
            localized = str(lang_labels.get(lk) or "").strip()
            if localized:
                candidates.extend((f"{localized}:", localized))
        for prefix in candidates:
            if t == prefix.rstrip(":"):
                return labels[lk]
            if t.startswith(prefix):
                rest = t[len(prefix):].strip(" :")
                if rest:
                    return f"{labels[lk]}: {rest}"
                return labels[lk]
    return t



_TASK_IN_LABEL_RE = re.compile(r"\b([A-Za-z][A-Za-z0-9_.-]*\[\d+\])")
_CORE_IN_LABEL_RE = re.compile(r"\b(?:Core[_\s-]?(\d+)|C(\d+))\b", re.IGNORECASE)
_DUR_IN_LABEL_RE = re.compile(r"\bdur(?:ation)?\s*=\s*([0-9]+(?:\.[0-9]+)?)", re.IGNORECASE)


def _normalize_evidence_item(
    ev: Any,
    *,
    default_task: str = "",
    default_core: str = "",
    label: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    """Copy evidence fields the Evidence table needs (task / core / duration)."""
    if not isinstance(ev, dict):
        return None
    out_label = str(
        label if label is not None else (ev.get("label") or ev.get("text") or "evidence")
    ).strip() or "evidence"
    task = str(ev.get("task") or default_task or "").strip()
    core = str(ev.get("core") or default_core or "").strip()
    time = ev.get("time")
    start = ev.get("start")
    stop = ev.get("stop")
    duration = ev.get("duration", ev.get("gap"))
    if start is None and time is not None:
        start = time
    if stop is None and start is not None and duration is not None:
        try:
            stop = float(start) + float(duration)
        except (TypeError, ValueError):
            stop = None
    item: Dict[str, Any] = {"label": out_label, "time": time}
    if task:
        item["task"] = task
    if core:
        item["core"] = core
    if start is not None:
        item["start"] = start
    if stop is not None:
        item["stop"] = stop
    if duration is not None:
        item["duration"] = duration
    return item

CONCLUSION_STATUSES: Tuple[str, ...] = (
    "confirmed", "correlated", "suspected", "not_observed", "insufficient",
)


def conclusion_status_from_payload(data: Optional[Dict[str, Any]] = None) -> str:
    """Map evidence payload fields onto a reader-facing conclusion status."""
    payload = data if isinstance(data, dict) else {}
    quality = payload.get("evidence_quality") if isinstance(
        payload.get("evidence_quality"), dict) else {}
    band = str(quality.get("band") or "").strip().lower()
    flags = quality.get("flags") if isinstance(quality.get("flags"), dict) else {}
    evidence = [e for e in (payload.get("evidence") or []) if isinstance(e, dict)]
    checks = [c for c in (payload.get("checks") or []) if isinstance(c, dict)]
    validation = payload.get("validation") if isinstance(
        payload.get("validation"), dict) else {}
    conf = str(payload.get("confidence") or "").strip().lower()

    if band == "insufficient":
        return "insufficient"
    if not evidence and not str(payload.get("conclusion") or "").strip():
        return "insufficient"
    if not evidence and checks and all(
        str(c.get("status") or "").lower() in (
            "not observed", "not_observed", "absent", "none", "")
        for c in checks
    ):
        return "not_observed"
    if band == "strong" and (flags.get("direct_evidence") or evidence):
        if validation and validation.get("ok") is False:
            return "suspected"
        return "confirmed"
    if band in ("medium-high", "medium") and evidence:
        return "correlated"
    if conf in ("high",) and evidence and band in ("strong", "medium-high", ""):
        if band == "insufficient":
            return "insufficient"
        return "confirmed" if band == "strong" else "correlated"
    if evidence or str(payload.get("conclusion") or "").strip():
        return "suspected"
    return "insufficient"


def _format_evidence_duration(start: Any, stop: Any) -> str:
    try:
        lo = float(start)
        hi = float(stop)
    except (TypeError, ValueError):
        return ""
    if not (hi > lo):
        return ""
    delta = hi - lo
    # Prefer µs for sub-second spans; otherwise seconds.
    if delta < 1.0:
        return f"{delta * 1_000_000:.0f} µs"
    if delta < 1000.0:
        return f"{delta:.6g} s"
    return f"{delta:.0f}"


def _format_evidence_duration_delta(delta: Any) -> str:
    try:
        d = float(delta)
    except (TypeError, ValueError):
        return ""
    if not (d > 0):
        return ""
    return _format_evidence_duration(0, d)


def _evidence_row_fields(ev: dict) -> Tuple[str, str, str, str, str]:
    label = str(ev.get("label") or "").strip() or "item"
    task = str(ev.get("task") or "").strip()
    core = str(ev.get("core") or "").strip()
    if not task:
        m = _TASK_IN_LABEL_RE.search(label)
        if m:
            task = m.group(1)
    if not core:
        m = _CORE_IN_LABEL_RE.search(label)
        if m:
            core = f"Core {m.group(1) or m.group(2)}"
    start, stop, t = ev.get("start"), ev.get("stop"), ev.get("time")
    dur = _format_evidence_duration(start, stop)
    if not dur:
        dur = _format_evidence_duration_delta(ev.get("duration", ev.get("gap")))
    if not dur:
        m = _DUR_IN_LABEL_RE.search(label)
        if m:
            dur = _format_evidence_duration_delta(m.group(1))
    try:
        s_lo = float(start) if start is not None else None
        s_hi = float(stop) if stop is not None else None
    except (TypeError, ValueError):
        s_lo = s_hi = None
    if s_lo is not None and s_hi is not None and s_hi > s_lo:
        time_cell = (
            f"jump:{_evidence_jump_token(s_lo)}–jump:{_evidence_jump_token(s_hi)}"
        )
    elif t is not None:
        time_cell = f"jump:{_evidence_jump_token(t)}"
    else:
        time_cell = "—"
    return time_cell, label, task or "—", core or "—", dur or "—"


def _wrap_evidence_fold(
    summary: str,
    body_lines: Any,
    *,
    open: bool = False,
    nested: bool = False,
) -> List[str]:
    """Wrap markdown body in a collapsible ``<details class="ai-ev-fold">`` block."""
    if isinstance(body_lines, (list, tuple)):
        raw = [line for line in body_lines if line is not None and str(line)]
    else:
        raw = [body_lines] if body_lines is not None and str(body_lines) else []
    body = "\n".join(str(line) for line in raw).strip()
    if not body:
        return []
    title = str(summary or "").strip() or "Details"
    open_attr = " open" if open else ""
    level_cls = "ai-ev-fold-l2" if nested else "ai-ev-fold-l1"
    return [
        f'<details class="ai-ev-fold {level_cls}"{open_attr}>',
        f"<summary>{title}</summary>",
        "",
        body,
        "",
        "</details>",
    ]


class _DirectEvidenceTable(NamedTuple):
    lines: List[str]
    timeline_only: bool
    count: int


def _format_direct_evidence_table(
    evidence: Sequence[Any], labels: Dict[str, str],
) -> _DirectEvidenceTable:
    """Format direct evidence as a markdown table.

    Timeline-only hits (no task/core/duration) render as a Time list.
    Empty columns are omitted when every row lacks that field.
    """
    rows = [e for e in evidence if isinstance(e, dict)]
    if not rows:
        return _DirectEvidenceTable([], False, 0)
    fields: List[Tuple[str, str, str, str, str]] = []
    for ev in rows[:20]:
        time_cell, label, task, core, dur = _evidence_row_fields(ev)
        origin = str(
            ev.get("origin") or ev.get("source") or ev.get("result_kind") or ""
        ).strip().lower()
        if origin in ("measured", "observed", "direct"):
            label = f"[measured] {label}"
        elif origin in ("derived", "computed"):
            label = f"[derived] {label}"
        elif origin in ("heuristic", "estimate"):
            label = f"[heuristic] {label}"
        elif origin in ("simulated", "simulation", "what_if"):
            label = f"[simulated] {label}"
        fields.append((time_cell, label, task, core, dur))
    has_task = any(r[2] != "—" for r in fields)
    has_core = any(r[3] != "—" for r in fields)
    has_dur = any(r[4] != "—" for r in fields)
    timeline_only = not has_task and not has_core and not has_dur
    if timeline_only:
        lines = [
            f"| {labels.get('col_time', 'Time')} |",
            "| --- |",
        ]
        for time_cell, *_rest in fields:
            lines.append(f"| {time_cell} |")
        return _DirectEvidenceTable(lines, True, len(fields))
    headers = [labels.get("col_time", "Time")]
    idxs = [0]
    headers.append(labels.get("col_event", "Observed event"))
    idxs.append(1)
    if has_task:
        headers.append(labels.get("col_task", "Task"))
        idxs.append(2)
    if has_core:
        headers.append(labels.get("col_core", "Core"))
        idxs.append(3)
    if has_dur:
        headers.append(labels.get("col_duration", "Duration"))
        idxs.append(4)
    sep = " | ".join("---:" if i == 4 else "---" for i in idxs)
    lines = [
        f"| {' | '.join(headers)} |",
        f"| {sep} |",
    ]
    for row in fields:
        lines.append(f"| {' | '.join(row[i] for i in idxs)} |")
    return _DirectEvidenceTable(lines, False, len(fields))


def _coverage_check_rows(
    coverage: Optional[dict], checks: Sequence[Any], labels: Dict[str, str],
) -> List[Tuple[str, str]]:
    """Build Checks table rows from coverage flags and tool checklist."""
    out: List[Tuple[str, str]] = []
    cov = coverage if isinstance(coverage, dict) else {}
    flags = cov.get("flags") if isinstance(cov.get("flags"), dict) else {}
    # Prefer explicit checklist entries when present.
    for c in checks:
        if not isinstance(c, dict):
            continue
        name = str(c.get("label") or c.get("metric") or labels.get("check", "check"))
        status = _localize_evidence_token(str(c.get("status") or ""), labels)
        detail = str(c.get("detail") or "").strip()
        cell = status if not detail else f"{status} — {detail}"
        out.append((name, cell or labels.get("not_evaluated", "Not evaluated")))
    if out:
        return out
    mapping = [
        ("directly_observed", labels.get("coverage_observed", "Blocking/off-CPU")),
        ("timeline_verified", labels.get("coverage_timeline", "Timeline")),
        ("metric_verified", labels.get("coverage_metric", "Metric")),
    ]
    observed = labels.get("observed", "Observed")
    not_obs = labels.get("not_observed", "Not observed")
    insuff = labels.get("insufficient_evidence", "Insufficient evidence")
    if cov.get("directly_observed") is not None or flags:
        # Count-style coverage from compute_evidence_coverage
        for key, title in (
            ("directly_observed", labels.get("coverage_observed", "Directly observed")),
            ("timeline_verified", labels.get("coverage_timeline", "Timeline verified")),
            ("metric_verified", labels.get("coverage_metric", "Metric verified")),
            ("unverified_assumptions", labels.get(
                "coverage_unverified", "Unverified assumptions")),
        ):
            val = cov.get(key)
            if val is None:
                continue
            try:
                n = int(val)
            except (TypeError, ValueError):
                out.append((title, str(val)))
                continue
            if key == "unverified_assumptions":
                cell = insuff if n > 0 else observed
            else:
                cell = observed if n > 0 else not_obs
            out.append((title, cell))
        return out
    qflags = flags
    # quality flags reused if coverage empty — caller may pass quality.flags
    return out


# Master expand/collapse targets every ai-ev-fold (not the top-level panel body).
# Keep in sync with web/src/utils/aiInvestigation.js EVIDENCE_SUBFOLDS_ALL.
EVIDENCE_SUBFOLDS_ALL = "ev-subfolds-all"
# Legacy id; do not use for new code.
EVIDENCE_PANEL_MESSAGE_FOLD_ID = EVIDENCE_SUBFOLDS_ALL


def evidence_panel_summary_line(text: str) -> str:
    """First verdict line for the collapsed Evidence & Validation header."""
    for line in str(text or "").replace("\r\n", "\n").split("\n"):
        s = line.strip()
        if s:
            return re.sub(r"\*\*", "", s)
    return ""


def _evidence_fold_id(title: str, body: str) -> str:
    """Stable id for an ai-ev-fold block. Keep in sync with ai_assistant._ev_fold_id."""
    raw = f"{str(title or '').strip()}\n{str(body or '').strip()[:160]}"
    return hashlib.sha1(raw.encode("utf-8", "replace")).hexdigest()[:12]


def _parse_evidence_fold_blocks(text: str) -> List[Tuple[str, str]]:
    """Return (summary, body) for each ``<details class=\"ai-ev-fold\">`` block, depth-first."""
    lines = str(text or "").replace("\r\n", "\n").split("\n")
    blocks: List[Tuple[str, str]] = []
    i = 0
    n = len(lines)
    while i < n:
        stripped = lines[i].strip()
        if re.match(r"^<details\b", stripped, re.I) and "ai-ev-fold" in stripped:
            i += 1
            summary = ""
            body_lines: List[str] = []
            depth = 1
            while i < n and depth > 0:
                s = lines[i].strip()
                if re.match(r"^<details\b", s, re.I):
                    depth += 1
                    body_lines.append(lines[i])
                    i += 1
                    continue
                if re.match(r"^</details>\s*$", s, re.I):
                    depth -= 1
                    if depth > 0:
                        body_lines.append(lines[i])
                    i += 1
                    continue
                if not summary and re.match(r"^<summary>", s, re.I):
                    summary = re.sub(
                        r"^<summary>", "", s, count=1, flags=re.I)
                    summary = re.sub(
                        r"</summary>\s*$", "", summary, count=1, flags=re.I
                    ).strip()
                    i += 1
                    continue
                body_lines.append(lines[i])
                i += 1
            body_text = "\n".join(body_lines).strip()
            title = summary or "Details"
            blocks.append((title, body_text))
            blocks.extend(_parse_evidence_fold_blocks(body_text))
            continue
        i += 1
    return blocks


def evidence_panel_inner_fold_ids(text: str) -> Tuple[str, ...]:
    """Fold ids for every nested ai-ev-fold section in evidence markdown."""
    return tuple(
        _evidence_fold_id(title, body)
        for title, body in _parse_evidence_fold_blocks(text)
    )


def evidence_panel_toggle_label(
    expanded: bool,
    response_language: str = "English",
) -> str:
    labels = evidence_panel_labels(response_language)
    if expanded:
        return str(labels.get("collapse_all") or "Collapse all")
    return str(labels.get("expand_all") or "Expand all")


def format_evidence_panel_markdown(
    data: Optional[Dict[str, Any]],
    response_language: str = "English",
) -> str:
    """Markdown for Evidence & Validation (panel + conversation log + export)."""
    if not isinstance(data, dict):
        return ""
    labels = evidence_panel_labels(response_language)
    lines: List[str] = []
    details: List[str] = []

    status_key = conclusion_status_from_payload(data)
    status_label = {
        "confirmed": labels.get("status_confirmed", "Confirmed"),
        "correlated": labels.get("status_correlated", "Correlated"),
        "suspected": labels.get("status_suspected", "Suspected"),
        "not_observed": labels.get("status_not_observed", "Not observed"),
        "insufficient": labels.get("status_insufficient", "Insufficient data"),
    }.get(status_key, labels.get("status_suspected", "Suspected"))

    coverage = data.get("coverage") if isinstance(data.get("coverage"), dict) else {}
    quality = data.get("evidence_quality") if isinstance(
        data.get("evidence_quality"), dict) else {}
    conf_raw = str(data.get("confidence") or "").strip()
    conf_label = _localize_evidence_token(conf_raw, labels) if conf_raw else ""
    if status_key == "insufficient" and conf_label.lower() == str(
            labels.get("high", "High")).lower():
        conf_label = labels.get("low", "Low")
    cov_pct = 0
    try:
        cov_pct = int(coverage.get("percent") or 0)
    except (TypeError, ValueError):
        cov_pct = 0
    if cov_pct >= 80:
        cov_label = labels.get("coverage_complete", "Complete")
    elif cov_pct >= 40:
        cov_label = labels.get("coverage_partial", "Partial")
    elif coverage or quality:
        cov_label = labels.get("coverage_missing", "Missing")
    else:
        cov_label = "—"
    band = str(quality.get("band") or "").strip().lower()
    evidence_label = {
        "strong": labels.get("quality_direct", "Direct"),
        "medium-high": labels.get("status_correlated", "Correlated"),
        "medium": labels.get("status_correlated", "Correlated"),
        "weak": labels.get("quality_possible", "Possible"),
        "insufficient": labels.get("status_insufficient", "Insufficient"),
    }.get(band, labels.get("quality_possible", "Possible") if quality else "—")
    lines.append(
        f"**{labels.get('verdict', 'Verdict')}:** {status_label}"
        f" · **{labels.get('coverage_short', 'Coverage')}:** {cov_label}"
        f" · **{labels.get('evidence_short', 'Evidence')}:** {evidence_label}"
        f" · **{labels.get('confidence', 'Confidence')}:** "
        f"{conf_label or '—'}"
    )

    conclusion = _localize_evidence_token(
        str(data.get("conclusion") or "").strip(), labels)
    if conclusion:
        lines.append("")
        # Gate Root cause vs Leading explanation on confirmation strength.
        finding_hdr = labels.get("finding", "Finding")
        if status_key == "confirmed" and str(
                data.get("confidence") or "").strip().lower() in ("high",):
            finding_hdr = labels.get("root_cause", "Root cause")
        elif status_key in ("confirmed", "correlated", "suspected"):
            finding_hdr = labels.get(
                "leading_explanation", "Leading explanation")
        lines.append(f"**{finding_hdr}**")
        lines.append(conclusion)
    subtitle = str(data.get("subtitle") or "").strip()
    # Subtitle that is only a mode/scope tag stays under Finding as a short line.
    if subtitle and not data.get("evidence_chain"):
        lines.append(subtitle[:320])

    interpreted = data.get("interpreted")
    if isinstance(interpreted, dict) and (
        interpreted.get("interpreted_question") or interpreted.get("scope")
    ):
        lines.append("")
        lines.append(format_scope_action_links(interpreted, labels))

    experiment = data.get("experiment")
    if isinstance(experiment, dict) and experiment.get("result"):
        lines.append("")
        lines.append(
            f"**{labels.get('experiment_result', 'Experiment result')}:** "
            f"{experiment.get('result')}"
        )
        verdict = str(
            experiment.get("verdict") or format_experiment_verdict(experiment)
        ).strip()
        if verdict:
            lines.append(f"**{verdict}**")
        lines.append(
            f"[{labels.get('save_knowledge', 'Save to knowledge')}]"
            f"({btf_exp_href('save', 'all')})"
        )

    evidence = data.get("evidence") or []
    table_info = _format_direct_evidence_table(evidence, labels)
    if table_info.lines:
        if table_info.timeline_only:
            title = (
                f"{labels.get('timeline_evidence', 'Timeline evidence')} · "
                f"{table_info.count}"
            )
        else:
            title = (
                f"{labels.get('direct_evidence', labels['evidence'])} · "
                f"{table_info.count} {labels.get('rows_label', 'rows')}"
            )
        lines.append("")
        lines.extend(_wrap_evidence_fold(
            title, table_info.lines, open=table_info.count <= 5,
        ))

    chain = str(data.get("evidence_chain") or "").strip()
    if chain:
        lines.append("")
        lines.append(f"**{labels.get('interpretation', labels['evidence_chain'])}**")
        lines.append(chain)
    elif subtitle and data.get("evidence"):
        # Prefer interpretation wording when we only have a free-text subtitle.
        pass

    checks = [c for c in (data.get("checks") or []) if isinstance(c, dict)]
    check_rows = _coverage_check_rows(coverage, checks, labels)
    if not check_rows:
        quality = data.get("evidence_quality") if isinstance(
            data.get("evidence_quality"), dict) else {}
        qflags = quality.get("flags") if isinstance(quality.get("flags"), dict) else {}
        if qflags:
            mapping = [
                ("direct_evidence", labels.get("quality_direct", "Direct evidence"),
                 labels.get("observed", "Observed"),
                 labels.get("not_observed", "Not observed")),
                ("timeline_correlation", labels.get(
                    "quality_timeline", "Timeline correlation"),
                 labels.get("observed", "Observed"),
                 labels.get("not_observed", "Not observed")),
                ("metric_correlation", labels.get(
                    "quality_metric", "Metric correlation"),
                 labels.get("observed", "Observed"),
                 labels.get("not_observed", "Not observed")),
            ]
            for fk, title, yes, no in mapping:
                val = qflags.get(fk)
                if val is True:
                    check_rows.append((title, yes))
                elif val is False:
                    check_rows.append((title, no))
                elif val is not None:
                    check_rows.append((
                        title,
                        _localize_evidence_token(str(val), labels),
                    ))
    if check_rows:
        check_body = [
            f"| {labels.get('check_header', 'Check')} "
            f"| {labels.get('status', 'Status')} |",
            "| --- | --- |",
        ]
        for name, cell in check_rows[:12]:
            check_body.append(f"| {name} | {cell} |")
        lines.append("")
        lines.extend(_wrap_evidence_fold(
            f"{labels.get('checks', labels.get('checklist', 'Checks'))} · "
            f"{len(check_rows)}",
            check_body,
            open=False,
        ))

    hyps_m = [h for h in (data.get("hypotheses_managed") or []) if isinstance(h, dict)]
    alts = [a for a in (data.get("alternatives") or []) if isinstance(a, dict)]
    alt_src = hyps_m or alts
    if alt_src:
        alt_lines: List[str] = []
        for h in alt_src[:8]:
            hyp = str(h.get("hypothesis") or "").strip()
            if not hyp:
                continue
            status = _localize_evidence_token(
                str(h.get("status") or "needs_evidence"), labels)
            why = str(h.get("why") or "").strip()
            # Omit artificial percentage probabilities in the default view.
            hid = str(h.get("id") or "")
            actions = format_hypothesis_action_links(hid, labels) if hid else ""
            bit = f"- *{hyp}* ({status})"
            if why:
                bit += f" — {why}"
            if actions:
                bit += f" {actions}"
            alt_lines.append(bit)
        if hyps_m:
            alt_lines.append(
                f"[{labels.get('compare_action', 'Compare hypotheses')}]"
                f"({btf_hyp_href('compare', 'all')})"
            )
        keep_open = (
            status_key == "insufficient"
            or str(data.get("confidence") or "").lower() == "low"
            or status_key == "not_observed"
        )
        lines.append("")
        lines.extend(_wrap_evidence_fold(
            f"{labels['alternatives']} · {len(alt_src)}",
            alt_lines,
            open=keep_open,
        ))

    falsify = data.get("falsify") if isinstance(data.get("falsify"), dict) else {}
    supporting = [s for s in (falsify.get("supporting") or []) if s]
    disprove = [
        s for s in (falsify.get("disprove") or falsify.get("would_disprove") or [])
        if s
    ]
    contradicting = [
        s for s in (
            falsify.get("contradicting")
            or falsify.get("contradictions")
            or data.get("contradictions")
            or []
        )
        if s
    ]
    if supporting:
        support_lines = [f"- {s}" for s in supporting[:8]]
        lines.append("")
        lines.extend(_wrap_evidence_fold(
            f"{labels.get('supporting', 'Supporting')} · {len(supporting)}",
            support_lines,
            open=len(supporting) <= 3,
        ))
    if contradicting:
        lines.append("")
        lines.append(f"**{labels.get('contradicting', 'Contradicting')}**")
        for s in contradicting[:8]:
            lines.append(f"- {s}")
    if disprove:
        lines.append("")
        lines.append(f"**{labels.get('missing_evidence', 'Missing evidence')}**")
        for s in disprove:
            lines.append(f"- {s}")
    nxt = str(falsify.get("next_check") or "").strip()
    if nxt:
        lines.append("")
        lines.append(
            f"**▶ {labels.get('next_check', labels.get('next_action', 'Next check'))}:** "
            f"{nxt}"
        )

    # --- Investigation details (secondary / debug chrome) -----------------
    # Supporting / Missing / next check are promoted above when present.
    conf = data.get("confidence")
    if conf:
        # Do not promote High confidence when status is Insufficient.
        show_conf = not (
            status_key == "insufficient"
            and str(conf).strip().lower() in ("high", labels.get("high", "High").lower())
        )
        if show_conf:
            details.append(
                f"**{labels['confidence']}:** "
                f"{_localize_evidence_token(str(conf), labels)}"
            )
    score = data.get("evidence_score")
    quality = data.get("evidence_quality")
    if isinstance(quality, dict) and quality.get("bar"):
        details.append(
            f"**{labels.get('quality', labels['score'])}:** {quality['bar']}"
        )
        details.extend(format_quality_flag_lines(quality, labels))
    elif score is not None:
        bar = str(data.get("evidence_score_bar") or "")
        details.append(f"**{labels['score']}:** {bar}")
    if isinstance(coverage, dict) and coverage.get("bar"):
        details.append(
            f"**{labels.get('coverage', 'Evidence Coverage')}:** {coverage['bar']}"
        )
        details.extend(format_coverage_count_lines(coverage, labels))
    hk = data.get("historical_knowledge")
    if isinstance(hk, dict) and (
        hk.get("previous_issue") or hk.get("message") or hk.get("flags")
    ):
        details.append(f"**{labels.get('historical', 'Historical knowledge')}**")
        issue = str(hk.get("previous_issue") or "").strip()
        if issue:
            details.append(
                f"- {labels.get('previous_issue', 'Previous issue')}: {issue}"
            )
        fix = str(hk.get("known_fix") or "").strip()
        if fix:
            details.append(f"- {labels.get('known_fix', 'Known fix')}: {fix}")
        occ = str(hk.get("last_occurrence") or "").strip()
        if occ:
            details.append(
                f"- {labels.get('last_occurrence', 'Last occurrence')}: {occ}"
            )
        for flag in (hk.get("flags") or [])[:4]:
            details.append(f"- {flag}")
        typical = hk.get("typical") if isinstance(hk.get("typical"), dict) else {}
        current = hk.get("current") if isinstance(hk.get("current"), dict) else {}
        for key in ("migrations", "migration_rate", "blocking", "wcet"):
            if key in typical or key in current:
                t = typical.get(key)
                c = current.get(key)
                if t is not None:
                    details.append(
                        f"- {labels.get('typical_rate', 'Typical rate')} ({key}): {t:g}"
                    )
                if c is not None:
                    details.append(
                        f"- {labels.get('current_rate', 'Current')} ({key}): {c:g}"
                    )
        msg = str(hk.get("message") or "").strip()
        if msg and msg not in ("No historical match", "Within historical range"):
            details.append(f"- {msg}")
    validation = data.get("validation")
    if isinstance(validation, dict) and not validation.get("ok", True):
        n = int(validation.get("unverified") or len(validation.get("issues") or []))
        details.append(
            f"**{labels.get('validation', 'Validation')}:** "
            f"{n} {labels.get('unverified', 'unverified claims')}"
        )
        for issue in (validation.get("issues") or [])[:6]:
            if isinstance(issue, dict):
                details.append(f"- {issue.get('kind')}: {issue.get('detail')}")
        for flag in (validation.get("flags") or [])[:6]:
            details.append(f"- {flag}")
    cost = str(data.get("cost") or "").strip()
    if cost:
        details.append(f"**{labels.get('cost', 'Investigation cost')}:** {cost}")
    evo = str(data.get("confidence_evolution") or "").strip()
    if evo:
        evo_lines = [
            f"- {line.strip()}" for line in evo.splitlines() if line.strip()
        ]
        details.extend(_wrap_evidence_fold(
            labels.get("evolution", "Confidence evolution"),
            evo_lines,
            open=False,
            nested=True,
        ))
    reasons = data.get("tool_reasons") or []
    if reasons:
        tool_lines: List[str] = []
        for r in reasons:
            if not isinstance(r, dict):
                continue
            tool = str(r.get("tool") or "")
            why = str(r.get("reason") or "")
            if tool:
                tool_lines.append(f"- {tool}: {why}")
        details.extend(_wrap_evidence_fold(
            f"{labels.get('tools_used', labels.get('investigation', 'Tools used'))} · "
            f"{len(tool_lines)}",
            tool_lines,
            open=False,
            nested=True,
        ))
    root_chain = data.get("root_cause_chain") or []
    hyps = data.get("hypotheses") or []
    if root_chain or hyps:
        tree_src = investigation_tree_mermaid(root_chain, hyps)
        if tree_src:
            details.extend(_wrap_evidence_fold(
                labels["tree"],
                ["```mermaid", tree_src.rstrip(), "```"],
                open=False,
                nested=True,
            ))
    graph_src = str(data.get("graph_mermaid") or "").strip()
    if graph_src:
        details.extend(_wrap_evidence_fold(
            labels.get("graph", "Evidence graph"),
            ["```mermaid", graph_src, "```"],
            open=False,
            nested=True,
        ))

    if details:
        lines.append("")
        lines.extend(_wrap_evidence_fold(
            labels.get("investigation_details", "Investigation details"),
            details,
            open=False,
        ))

    return "\n".join(lines).strip()


def format_investigation_plan_status(
    plan: Optional[Dict[str, Any]],
    response_language: str = "English",
) -> str:
    """One-line progress for the Investigation plan strip."""
    if not isinstance(plan, dict):
        return ""
    labels = evidence_panel_labels(response_language)
    steps = [s for s in (plan.get("steps") or []) if isinstance(s, dict)]
    total = len(steps)
    done = sum(1 for s in steps if str(s.get("status") or "") == "done")
    active = next(
        (s for s in steps if str(s.get("status") or "") == "active"), None)
    if active is None:
        active = next(
            (s for s in steps if str(s.get("status") or "") != "done"), None)
    step_label = str(
        (active or {}).get("label") or (active or {}).get("id") or ""
    ).strip()
    inv = labels["investigation"]
    if not total:
        return inv
    if done >= total:
        return f"{inv}  {done}/{total}  {labels['done']}"
    if step_label:
        return f"{inv}  {done}/{total}  {step_label}"
    return f"{inv}  {done}/{total}"


_REGRESSION_TYPES: Tuple[str, ...] = (
    "execution", "scheduling", "synchronization", "migration",
    "load_balance", "unknown",
)

_REGRESSION_TYPE_BY_METRIC: Dict[str, str] = {
    "migrations": "migration",
    "migrated_tasks": "migration",
    "load_balance_score": "load_balance",
    "load_balance_sigma": "load_balance",
    "missed_ticks": "scheduling",
    "tick_health": "scheduling",
    "context_switches": "scheduling",
    "blocking_max_us": "synchronization",
    "response_us": "synchronization",
    "wcet_us": "execution",
    "exec_max_us": "execution",
}

_REGRESSION_TYPE_KEYWORDS: Tuple[Tuple[str, str], ...] = (
    ("migrat", "migration"),
    ("load_balance", "load_balance"),
    ("load balance", "load_balance"),
    ("tick", "scheduling"),
    ("context_switch", "scheduling"),
    ("mutex", "synchronization"),
    ("block", "synchronization"),
    ("inversion", "synchronization"),
    ("inherit", "synchronization"),
    ("wcet", "execution"),
    ("exec", "execution"),
    ("cpu", "execution"),
)


def classify_regression_type(
    checks: Optional[Sequence[dict]] = None,
    primary: Optional[Dict[str, Any]] = None,
) -> str:
    """Best-effort ``regression_type`` from the primary/failing metric delta(s)."""
    def _type_for(check: Optional[Dict[str, Any]]) -> str:
        if not isinstance(check, dict):
            return ""
        mid = str(check.get("id") or "").strip().lower()
        if mid in _REGRESSION_TYPE_BY_METRIC:
            return _REGRESSION_TYPE_BY_METRIC[mid]
        blob = f"{check.get('id') or ''} {check.get('label') or ''}".lower()
        for kw, rtype in _REGRESSION_TYPE_KEYWORDS:
            if kw in blob:
                return rtype
        return ""

    rtype = _type_for(primary)
    if rtype:
        return rtype
    for c in checks or []:
        if isinstance(c, dict) and c.get("status") == "fail":
            rtype = _type_for(c)
            if rtype:
                return rtype
    return "unknown"


def compare_performance_metrics(
    candidate: Dict[str, Any],
    baseline: Dict[str, Any],
    *,
    label_a: str = "A",
    label_b: str = "B",
) -> Dict[str, Any]:
    """Structured A vs B performance deltas using regression rules."""
    snap_a = candidate if "metrics" in (candidate or {}) else {
        "metrics": dict(candidate or {}),
    }
    snap_b = baseline if "metrics" in (baseline or {}) else {
        "metrics": dict(baseline or {}),
    }
    result = evaluate_regression(snap_a, snap_b)
    primary = next((c for c in result.get("checks") or [] if c.get("status") == "fail"), None)
    if primary is None:
        primary = next((c for c in result.get("checks") or [] if c.get("status") == "pass"), None)
    confidence = "High" if primary and primary.get("status") == "fail" else (
        "Medium" if primary else "Low"
    )
    regression_type = classify_regression_type(result.get("checks"), primary)
    return {
        "ok": True,
        "message": str(result.get("summary") or "compared"),
        "label_a": label_a,
        "label_b": label_b,
        "failed": bool(result.get("failed")),
        "checks": result.get("checks") or [],
        "primary_regression": primary,
        "confidence": confidence,
        "regression_type": regression_type,
        "evidence_quality": (
            "Directly observed" if primary else "Insufficient evidence"
        ),
        "suggested_tools": [
            {"name": "investigate", "arguments": {}, "reason": "Drill into top finding"},
            {"name": "correlate_events", "arguments": {}, "reason": "Timeline correlation"},
        ],
        "report": format_regression_report(
            result, title=f"{label_a} vs {label_b}",
        ),
    }


_MUTEX_ADDR_RE = re.compile(r"mutex\D{0,12}(0x[0-9a-fA-F]+)", re.IGNORECASE)


def _pi_context_from_findings(
    findings: Sequence[dict],
    low: str,
    mediums: Sequence[str],
) -> Tuple[str, str]:
    """Best-effort ``(mutex_addr, high_task)`` scan of finding text.

    PI episodes only track the boosted (``low``) task and its ``medium``
    interlopers; the blocked high-priority waiter and mutex identity, when
    known, usually only show up in the free-text Analysis Findings.
    """
    exclude = {str(low or "").lower()} | {str(m or "").lower() for m in mediums}
    for f in findings or []:
        blob = f"{f.get('title') or ''} {f.get('text') or ''}"
        if str(low or "").lower() not in blob.lower():
            continue
        mutex = ""
        m = _MUTEX_ADDR_RE.search(blob)
        if m:
            mutex = m.group(1)
        high = ""
        for tok in re.findall(r"\b[A-Za-z_][\w]*\[[0-9]+\]", blob):
            if tok.lower() not in exclude:
                high = tok
                break
        if mutex or high:
            return mutex, high
    return "", ""


def detect_priority_inversion(
    episodes: Sequence[dict],
    findings: Optional[Sequence[dict]] = None,
    *,
    task: str = "",
    window: Optional[float] = None,
) -> Dict[str, Any]:
    """Best-effort priority-inversion detection from PI episodes + findings.

    ``episodes`` are raw priority_inheritance rows (see ``query_raw_metric``),
    each carrying its own ``task`` label. Only episodes flagged
    ``inversion_suspect`` are reported; mutex address and the blocked
    high-priority task are inferred from ``findings`` text when available.
    ``window`` is an optional minimum-duration hint (ns) used to drop
    inversion episodes too short to matter.
    """
    task = str(task or "").strip()
    rows = [e for e in (episodes or []) if isinstance(e, dict)]

    def _row_matches_task(e: dict) -> bool:
        if str(e.get("task") or "").strip().lower() == task.lower():
            return True
        for m in e.get("medium_tasks") or []:
            label = m.get("label") if isinstance(m, dict) else m
            if str(label or "").strip().lower() == task.lower():
                return True
        return False

    if task:
        rows = [e for e in rows if _row_matches_task(e)]

    win: Optional[float] = None
    if window is not None:
        try:
            win = float(window)
        except (TypeError, ValueError):
            win = None

    def _duration(e: dict) -> Optional[float]:
        dur = e.get("duration")
        if dur is not None:
            try:
                return float(dur)
            except (TypeError, ValueError):
                return None
        start, stop = e.get("start"), e.get("stop")
        if start is None or stop is None:
            return None
        try:
            return float(stop) - float(start)
        except (TypeError, ValueError):
            return None

    if win and win > 0:
        rows = [e for e in rows if (_duration(e) is None or _duration(e) >= win)]

    suspects = [e for e in rows if e.get("inversion_suspect")]
    items = enrich_findings_with_ids(findings) if findings else []
    inversions: List[Dict[str, Any]] = []
    for e in suspects:
        low_label = str(e.get("task") or task or "").strip() or "?"
        mediums = [
            str(m.get("label") if isinstance(m, dict) else m).strip()
            for m in (e.get("medium_tasks") or [])
        ]
        mediums = [m for m in mediums if m]
        mutex, high = _pi_context_from_findings(items, low_label, mediums)
        start = e.get("start")
        stop = e.get("stop")
        duration = e.get("duration")
        if duration is None and start is not None and stop is not None:
            try:
                duration = int(stop) - int(start)
            except (TypeError, ValueError):
                duration = None
        inversions.append({
            "high": high,
            "medium": mediums[0] if mediums else "",
            "medium_tasks": mediums,
            "low": low_label,
            "mutex": mutex,
            "time": start,
            "duration": duration,
            "base_pri": e.get("base_pri"),
            "peak_pri": e.get("peak_pri"),
            "pattern": e.get("pattern") or "",
        })
    inversions.sort(key=lambda r: (r.get("time") is None, r.get("time")))
    if not rows:
        confidence = "Low"
    elif any(inv.get("high") and inv.get("mutex") for inv in inversions):
        confidence = "High"
    elif inversions:
        confidence = "Medium"
    else:
        confidence = "Low"
    focus_task = task or (inversions[0]["low"] if inversions else "")
    return {
        "ok": True,
        "message": (
            f"{len(inversions)} priority inversion(s) detected"
            if inversions else "No priority inversion suspects in scope"
        ),
        "task": task,
        "inversions": inversions,
        "count": len(inversions),
        "confidence": confidence,
        "suggested_tools": [
            {
                "name": "query_raw_metric",
                "arguments": {"task": focus_task, "metric": "priority_inheritance"},
                "reason": "Inspect raw PI boost episodes",
            },
            {
                "name": "correlate_events",
                "arguments": {"task": focus_task},
                "reason": "Cross-task timeline around the inversion",
            },
        ] if focus_task else [],
    }


_STOPWORDS = frozenset({
    "the", "a", "an", "and", "or", "of", "to", "in", "on", "for", "with",
    "is", "are", "this", "that", "at", "by", "from", "into", "than", "was",
    "were", "has", "have", "had", "its", "it's", "task", "tasks",
})

_RELATED_METRIC_KEYWORDS: Dict[str, Tuple[str, ...]] = {
    "priority_inheritance": ("inversion", "inherit", "priority", "l/m/h", "mutex", "boost"),
    "execution": ("wcet", "cpu", "execution", "spike", "slice"),
    "migrations": ("migrat", "thrash", "bounc", "core"),
    "blocking": ("block", "latency", "wait", "dispatch"),
    "sync": ("mutex", "semaphore", "lock", "sync"),
    "findings": (),
}


def _finding_keywords(f: dict) -> set:
    blob = f"{f.get('title') or ''} {f.get('text') or ''}".lower()
    tokens = re.findall(r"[a-z][a-z0-9_]{3,}", blob)
    return {t for t in tokens if t not in _STOPWORDS}


def _finding_evidence_times(f: dict) -> List[float]:
    times: List[float] = []
    for ev in f.get("evidence") or []:
        if isinstance(ev, dict) and ev.get("time") is not None:
            try:
                times.append(float(ev.get("time")))
            except (TypeError, ValueError):
                continue
    return times


def find_related_findings(
    findings: Sequence[dict],
    *,
    finding_id: str = "",
    task: str = "",
    metric: str = "",
    window: Optional[float] = None,
    limit: int = 10,
) -> Dict[str, Any]:
    """Relate enriched findings by shared task, keyword, or severity adjacency."""
    limit = max(1, min(40, int(limit or 10)))
    items = enrich_findings_with_ids(findings)
    if not items:
        return {
            "ok": False,
            "message": "No Analysis Findings in scope",
            "focus": None,
            "related": [],
            "count": 0,
        }
    focus = resolve_finding(items, finding_id) if finding_id else None
    task = str(task or "").strip()
    metric_key = str(metric or "").strip().lower()
    keywords = set(_RELATED_METRIC_KEYWORDS.get(metric_key, ()))
    focus_task = ""
    focus_keywords: set = set()
    focus_times: List[float] = []
    if focus is not None:
        focus_task = str(focus.get("task") or _guess_task_name(str(focus.get("text") or ""))).strip()
        focus_keywords = _finding_keywords(focus)
        focus_times = _finding_evidence_times(focus)

    win: Optional[float] = None
    if window is not None:
        try:
            win = float(window)
        except (TypeError, ValueError):
            win = None

    scored: List[Tuple[float, dict, List[str]]] = []
    for f in items:
        if focus is not None and f.get("id") == focus.get("id"):
            continue
        reasons: List[str] = []
        score = 0.0
        f_task = str(f.get("task") or _guess_task_name(str(f.get("text") or ""))).strip()
        if task and f_task and f_task.lower() == task.lower():
            score += 2.0
            reasons.append(f"shares task {f_task}")
        if focus_task and f_task and f_task.lower() == focus_task.lower() and not (
            task and f_task.lower() == task.lower()
        ):
            score += 2.0
            reasons.append(f"shares task {f_task}")
        if keywords:
            blob = f"{f.get('title')} {f.get('text')}".lower()
            hits = sorted(k for k in keywords if k in blob)
            if hits:
                score += 1.0 * len(hits)
                reasons.append(f"mentions {', '.join(hits)}")
        if focus_keywords:
            shared = sorted(focus_keywords & _finding_keywords(f))
            if shared:
                score += 0.5 * len(shared)
                reasons.append(f"shared keyword(s): {', '.join(shared)}")
        if win and win > 0 and focus_times:
            f_times = _finding_evidence_times(f)
            if any(abs(t - ft) <= win for t in focus_times for ft in f_times):
                score += 1.0
                reasons.append("within time window")
        if focus is not None and not reasons:
            f_rank = _SEV_RANK.get(str(f.get("severity") or "info").lower(), 3)
            focus_rank = _SEV_RANK.get(str(focus.get("severity") or "info").lower(), 3)
            if abs(f_rank - focus_rank) <= 1:
                score += 0.25
                reasons.append("adjacent severity")
        if score > 0:
            scored.append((score, f, reasons))
    scored.sort(key=lambda row: -row[0])
    related = [
        {
            "id": f.get("id"),
            "title": f.get("title"),
            "severity": f.get("severity"),
            "task": f.get("task") or _guess_task_name(str(f.get("text") or "")),
            "score": round(score, 2),
            "reasons": reasons,
        }
        for score, f, reasons in scored[:limit]
    ]
    return {
        "ok": True,
        "message": (
            f"{len(related)} related finding(s)"
            + (f" for {focus.get('id')}" if focus else "")
        ),
        "focus": (
            {"id": focus.get("id"), "title": focus.get("title")} if focus else None
        ),
        "related": related,
        "count": len(related),
    }


_COMPARE_TASK_METRIC_FIELDS: Dict[str, Tuple[str, ...]] = {
    "execution": ("count", "total", "max", "mean"),
    "blocking": ("count", "total", "max"),
    "migrations": ("count",),
    "priority_inheritance": ("count",),
}


def compare_tasks_metrics(
    task_a: str,
    task_b: str,
    data_a: Dict[str, Any],
    data_b: Dict[str, Any],
    *,
    metrics: Optional[Sequence[str]] = None,
) -> Dict[str, Any]:
    """Compare two tasks' execution/blocking/migrations/priority metrics.

    ``data_a`` / ``data_b`` are ``{metric: {field: value}}`` maps as returned
    by ``query_raw_metric`` for each metric (e.g. ``execution.count/total/
    max/mean``). Metrics with no data on either side are skipped.
    """
    wanted = [m for m in (metrics or list(_COMPARE_TASK_METRIC_FIELDS)) if m in _COMPARE_TASK_METRIC_FIELDS]
    if not wanted:
        wanted = list(_COMPARE_TASK_METRIC_FIELDS)
    data_a = data_a or {}
    data_b = data_b or {}
    rows: List[Dict[str, Any]] = []
    for metric in wanted:
        da = data_a.get(metric) if isinstance(data_a.get(metric), dict) else {}
        db = data_b.get(metric) if isinstance(data_b.get(metric), dict) else {}
        if not da and not db:
            continue
        for field in _COMPARE_TASK_METRIC_FIELDS[metric]:
            va = da.get(field)
            vb = db.get(field)
            delta = None
            pct = None
            if isinstance(va, (int, float)) and isinstance(vb, (int, float)):
                delta = va - vb
                pct = (100.0 * delta / vb) if vb else (100.0 if va else 0.0)
            rows.append({
                "metric": metric,
                "field": field,
                "a": va,
                "b": vb,
                "delta": delta,
                "delta_pct": round(pct, 1) if pct is not None else None,
            })
    ranked = sorted(
        (r for r in rows if r.get("delta_pct") is not None),
        key=lambda r: -abs(r["delta_pct"]),
    )
    primary = ranked[0] if ranked else None
    if primary and abs(primary["delta_pct"] or 0) >= 25:
        confidence = "High"
    elif primary:
        confidence = "Medium"
    else:
        confidence = "Low"
    return {
        "ok": True,
        "message": f"Compared {task_a} vs {task_b} across {len(wanted)} metric group(s)",
        "task_a": task_a,
        "task_b": task_b,
        "rows": rows,
        "primary_difference": primary,
        "confidence": confidence,
        "suggested_tools": [
            {"name": "correlate_events", "arguments": {"task": task_a},
             "reason": f"Timeline for {task_a}"},
            {"name": "correlate_events", "arguments": {"task": task_b},
             "reason": f"Timeline for {task_b}"},
        ],
    }


_REPORT_TYPES = frozenset({
    "executive", "performance", "root_cause", "regression",
    "optimization", "bug", "ci",
})


def _open_statistics_next_check(finding: Optional[dict]) -> str:
    """Concise clickable 'Open Statistics → …' line when inspect/task is known."""
    if not isinstance(finding, dict):
        return ""
    from .config import FINDING_SECTION_MAP  # late: avoid import cycles
    inspect = str(finding.get("inspect") or "").strip()
    task = str(finding.get("task") or "").strip()
    fid = str(finding.get("id") or "").strip()
    sid = str(FINDING_SECTION_MAP.get(fid) or "").strip()
    label = ""
    if inspect and task:
        section = inspect.split(" (", 1)[0].strip() or inspect
        label = f"Open {section} → {task}"
    elif inspect:
        section = inspect.split(" (", 1)[0].strip() or inspect
        label = f"Open {section}"
    elif task:
        label = f"Open Statistics → {task}"
    else:
        return ""
    if sid:
        return f"[{label}](btfstats:section/{sid})"
    return label


def generate_structured_report(
    findings: Sequence[dict],
    *,
    report_type: str = "performance",
    focus_id: str = "",
    compare: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Build markdown sections for generate_report (does not write a file)."""
    rtype = str(report_type or "performance").strip().lower().replace("-", "_")
    if rtype not in _REPORT_TYPES:
        rtype = "performance"
    items = enrich_findings_with_ids(findings)
    focus = resolve_finding(items, focus_id) if items else None
    anomalies = detect_anomalies(items, limit=8)
    chain = build_root_cause_chain(focus) if focus else []
    title_map = {
        "executive": "Executive summary",
        "performance": "Performance analysis",
        "root_cause": "Root-cause analysis",
        "regression": "Regression report",
        "optimization": "Optimization report",
        "bug": "Bug report",
        "ci": "CI report",
    }
    heading = title_map.get(rtype, "Performance analysis")
    lines = [f"# {heading}", ""]
    if focus:
        lines.extend([
            "## Summary",
            f"**{focus.get('title')}** ({focus.get('severity')})",
            "",
            str(focus.get("text") or ""),
            "",
        ])
    else:
        lines.extend(["## Summary", "No single focus finding; ranked anomalies below.", ""])
    lines.append("## Evidence")
    for a in (anomalies.get("anomalies") or [])[:6]:
        lines.append(
            f"{a.get('rank')}. [{a.get('band')}] {a.get('title')} — {a.get('id')}"
        )
    lines.append("")
    if chain:
        lines.append("## Root cause chain")
        for step in chain:
            lines.append(f"- **{step.get('label')}**: {step.get('detail') or ''}".rstrip())
        lines.append("")
    if compare:
        lines.append("## Comparison")
        lines.append(str(compare.get("report") or compare.get("message") or "").rstrip())
        lines.append("")
        primary = compare.get("primary_regression")
        if primary:
            lines.append(
                f"Primary: {primary.get('label')} — {primary.get('detail')} "
                f"(confidence {compare.get('confidence')})"
            )
            lines.append("")
    lines.extend([
        "## Confidence",
        "Medium — structured from Analysis Findings; confirm with tool evidence.",
        "",
        "## Next check",
    ])
    open_line = _open_statistics_next_check(focus)
    if open_line:
        lines.append(f"- {open_line}")
    lines.extend([
        "- Place cursors / zoom on the worst episode (`set_cursors`, `zoom_to_range`).",
        "- Highlight the focus task and verify on the timeline.",
        "- Re-run Trace Compare or `compare_performance` after a fix.",
        "",
    ])
    md = "\n".join(lines)
    return {
        "ok": True,
        "message": f"{heading} ({len(items)} findings)",
        "report_type": rtype,
        "title": heading,
        "markdown": md,
        "sections": {
            "summary": (focus or {}).get("text") or "",
            "findings": anomalies.get("anomalies") or [],
            "root_cause_chain": chain,
            "compare": compare,
        },
        "suggested_tools": [
            {"name": "export_report", "arguments": {"format": "html"},
             "reason": "Save HTML with diagrams and GUI state"},
        ],
    }


# --- Phase 2 / 3 helpers -------------------------------------------------

_BOOKMARK_KINDS = {
    "root_cause": ("🔴", "Root cause"),
    "evidence": ("🟠", "Important evidence"),
    "correlated": ("🟡", "Correlated event"),
    "reference": ("🟢", "Normal reference"),
}


def check_task_budgets(
    metrics_by_task: Sequence[dict],
    budgets: Optional[Dict[str, Dict[str, float]]] = None,
) -> Dict[str, Any]:
    """Compare per-task measured metrics against optional budgets.

    *metrics_by_task* items: ``{task, wcet_us?, response_us?, deadline_us?,
    exec_max_us?, blocking_max_us?}``.
    *budgets*: ``{task: {wcet_us, response_us, deadline_us}}``.
    """
    budgets = dict(budgets or {})
    rows: List[dict] = []
    violations = 0
    for item in metrics_by_task or []:
        if not isinstance(item, dict):
            continue
        task = str(item.get("task") or "").strip()
        if not task:
            continue
        bud = budgets.get(task) or budgets.get(task.split("[", 1)[0]) or {}
        checks = []
        for key, label in (
            ("wcet_us", "WCET"),
            ("response_us", "Response"),
            ("deadline_us", "Deadline"),
            ("exec_max_us", "Exec Max"),
            ("blocking_max_us", "Blocking Max"),
        ):
            measured = item.get(key)
            limit = bud.get(key) if key in bud else bud.get(key.replace("_max", ""))
            if measured is None:
                continue
            try:
                mval = float(measured)
            except (TypeError, ValueError):
                continue
            status = "info"
            detail = f"{mval:g} µs"
            if limit is not None:
                try:
                    lim = float(limit)
                except (TypeError, ValueError):
                    lim = None
                if lim is not None and lim > 0:
                    pct = 100.0 * (mval - lim) / lim
                    if mval > lim:
                        status = "fail"
                        violations += 1
                        detail = f"{mval:g} / {lim:g} µs (+{pct:.1f}%)"
                    else:
                        status = "pass"
                        detail = f"{mval:g} / {lim:g} µs"
            checks.append({"metric": key, "label": label, "status": status, "detail": detail})
        if checks:
            rows.append({"task": task, "checks": checks})
    return {
        "ok": True,
        "message": (
            f"{len(rows)} task budget row(s), {violations} violation(s)"
            if rows else "No budget metrics to check"
        ),
        "tasks": rows,
        "violations": violations,
        "budgets_applied": bool(budgets),
    }


def build_optimization_advice(
    findings: Sequence[dict],
    *,
    limit: int = 5,
) -> Dict[str, Any]:
    """Evidence-backed mitigation ideas from Analysis Findings."""
    limit = max(1, min(20, int(limit or 5)))
    items = enrich_findings_with_ids(findings)
    ranked = detect_anomalies(items, limit=limit)
    ideas: List[dict] = []
    for a in ranked.get("anomalies") or []:
        blob = f"{a.get('title')} {a.get('text')}".lower()
        task = a.get("task") or ""
        if "migrat" in blob or "thrash" in blob or "bounc" in blob:
            ideas.append({
                "title": f"Pin / affinity for {task or 'hot migrator'}",
                "expected_impact": "High",
                "risk": "Low",
                "why": a.get("text") or a.get("title"),
                "evidence_finding": a.get("id"),
            })
        elif "inversion" in blob or "mutex" in blob or "block" in blob:
            ideas.append({
                "title": "Reduce shared-lock contention / shorten critical section",
                "expected_impact": "High",
                "risk": "Medium",
                "why": a.get("text") or a.get("title"),
                "evidence_finding": a.get("id"),
            })
        elif "wcet" in blob or "spike" in blob or "cpu" in blob:
            ideas.append({
                "title": f"Profile and trim long slices on {task or 'hot task'}",
                "expected_impact": "Medium",
                "risk": "Medium",
                "why": a.get("text") or a.get("title"),
                "evidence_finding": a.get("id"),
            })
        elif "load" in blob or "balance" in blob:
            ideas.append({
                "title": "Rebalance task placement across cores",
                "expected_impact": "Medium",
                "risk": "Low",
                "why": a.get("text") or a.get("title"),
                "evidence_finding": a.get("id"),
            })
        else:
            ideas.append({
                "title": f"Investigate {a.get('title')}",
                "expected_impact": "Medium",
                "risk": "Low",
                "why": a.get("text") or "",
                "evidence_finding": a.get("id"),
            })
        if len(ideas) >= limit:
            break
    return {
        "ok": True,
        "message": f"{len(ideas)} optimization idea(s)",
        "recommendations": ideas,
        "disclaimer": "Simulation / estimate — not measured behavior",
    }


_REGRESSION_CLASSIFICATION_MAP: Dict[str, str] = {
    "migrations": "thrashing",
    "migrated_tasks": "thrashing",
    "load_balance": "load_imbalance",
    "missed_ticks": "tick_health",
}

_REGRESSION_CLASSIFICATION_LABELS: Dict[str, str] = {
    "thrashing": "Core thrashing / migration regression",
    "load_imbalance": "Load balance regression",
    "tick_health": "Tick health regression",
    "unclassified": "Unclassified regression",
    "none": "No regression",
}


def classify_regression(primary: Optional[Dict[str, Any]]) -> str:
    """Coarse category id for a compare_performance ``primary_regression`` check."""
    if not primary:
        return "none"
    return _REGRESSION_CLASSIFICATION_MAP.get(str(primary.get("id") or ""), "unclassified")


def explain_regression(
    compare: Dict[str, Any],
    findings: Optional[Sequence[dict]] = None,
) -> Dict[str, Any]:
    """Narrative explanation of a compare_performance / evaluate_regression result."""
    compare = dict(compare or {})
    primary = compare.get("primary_regression") or {}
    failed = bool(compare.get("failed"))
    label_a = compare.get("label_a") or "A"
    label_b = compare.get("label_b") or "B"
    classification = classify_regression(primary if failed else None)
    regression_type = str(
        compare.get("regression_type") or classify_regression_type(compare.get("checks"), primary)
    )
    causal_chain: List[Dict[str, Any]] = []
    if primary:
        synthetic_finding = {
            "id": "regression_primary",
            "title": f"Regression: {primary.get('label')}",
            "text": f"{primary.get('label')} changed — {primary.get('detail')}",
            "severity": "error" if failed else "info",
        }
        causal_chain = build_root_cause_chain(synthetic_finding)
    lines = [
        f"# Regression explanation — {label_a} vs {label_b}",
        "",
        str(compare.get("message") or ("REGRESSION DETECTED" if failed else "No regression")),
        "",
    ]
    if primary:
        lines.extend([
            "## Primary change",
            f"**{primary.get('label')}**: {primary.get('detail')}",
            f"Candidate={primary.get('candidate')}, Baseline={primary.get('baseline')}",
            "",
        ])
    lines.append("## Supporting checks")
    for c in compare.get("checks") or []:
        mark = {"pass": "✓", "fail": "✗", "skip": "·"}.get(c.get("status"), "?")
        lines.append(f"- {mark} {c.get('label')}: {c.get('detail')}")
    lines.append("")
    lines.extend([
        "## Classification",
        _REGRESSION_CLASSIFICATION_LABELS.get(classification, "Unclassified regression"),
        "",
    ])
    if causal_chain:
        lines.append("## Causal chain")
        for step in causal_chain:
            lines.append(f"- **{step.get('label')}**: {step.get('detail') or ''}".rstrip())
        lines.append("")
    anomalies = detect_anomalies(findings or [], limit=5) if findings else {"anomalies": []}
    if anomalies.get("anomalies"):
        lines.append("## Related findings on candidate")
        for a in anomalies["anomalies"][:5]:
            lines.append(f"- [{a.get('band')}] {a.get('title')} (`{a.get('id')}`)")
        lines.append("")
    conf = compare.get("confidence") or ("High" if failed else "Medium")
    lines.extend([
        f"## Confidence",
        f"{conf} — {compare.get('evidence_quality') or 'Directly observed metric deltas'}",
        "",
    ])
    suggested_tools = [
        {"name": "correlate_events", "arguments": {}, "reason": "Timeline for worst metric"},
        {"name": "investigate", "arguments": {}, "reason": "Root-cause chain"},
    ]
    if classification == "thrashing":
        suggested_tools.append({
            "name": "optimize_experiment", "arguments": {},
            "reason": "Rank pin / affinity candidates for the thrashing task",
        })
    elif classification == "load_imbalance":
        suggested_tools.append({
            "name": "analyze_traces", "arguments": {},
            "reason": "Rank all loaded traces by scheduling behavior",
        })
    elif classification == "tick_health":
        suggested_tools.append({
            "name": "check_budget", "arguments": {},
            "reason": "Verify WCET/response/deadline budgets after tick regressions",
        })
    return {
        "ok": True,
        "message": "Regression explained" if failed else "No regression to explain",
        "failed": failed,
        "markdown": "\n".join(lines),
        "primary_regression": primary,
        "classification": classification,
        "regression_type": regression_type,
        "causal_chain": causal_chain,
        "confidence": conf,
        "suggested_tools": suggested_tools,
    }


def format_bookmark_label(kind: str, note: str = "") -> str:
    """Semantic bookmark / annotation label (emoji + role + note)."""
    key = str(kind or "evidence").strip().lower().replace("-", "_").replace(" ", "_")
    if key in ("root", "cause", "rca"):
        key = "root_cause"
    if key in ("corr", "related"):
        key = "correlated"
    if key in ("ok", "normal", "ref"):
        key = "reference"
    emoji, role = _BOOKMARK_KINDS.get(key, _BOOKMARK_KINDS["evidence"])
    note = str(note or "").strip()
    if note:
        return f"{emoji} {role}: {note}"[:240]
    return f"{emoji} {role}"


def build_investigation_replay(
    *,
    finding: Optional[dict] = None,
    plan: Optional[Dict[str, Any]] = None,
    tools_run: Optional[Sequence[str]] = None,
    conclusion: str = "",
    evidence_times: Optional[Sequence[float]] = None,
    trace_name: str = "",
    scope: str = "",
    queries: Optional[Sequence[Dict[str, Any]]] = None,
    evidence: Optional[Sequence[Dict[str, Any]]] = None,
    confidence: str = "",
    alternatives: Optional[Sequence[Dict[str, Any]]] = None,
    timestamp: str = "",
) -> Dict[str, Any]:
    """Structured investigation replay card for UI / export.

    Additive fields (*trace_name*, *scope*, *queries*, *evidence*,
    *confidence*, *alternatives*, *timestamp*) make this usable as a full
    investigation export package (see ``build_investigation_package``).
    """
    tools_run = [str(t) for t in (tools_run or []) if t]
    plan = plan or default_investigation_plan(
        goal=f"Investigate: {(finding or {}).get('title') or 'finding'}"
    )
    if tools_run:
        plan = mark_plan_steps_from_tools(plan, tools_run)
    steps = []
    for s in plan.get("steps") or []:
        steps.append({
            "id": s.get("id"),
            "label": s.get("label"),
            "status": s.get("status"),
        })
    times = []
    for t in evidence_times or []:
        try:
            times.append(float(t))
        except (TypeError, ValueError):
            pass
    suggested: List[Dict[str, Any]] = []
    if times:
        suggested.append({
            "name": "set_cursors",
            "arguments": {"timestamps": times[:8]},
            "reason": "Replay evidence cursors",
        })
    suggested.append({
        "name": "generate_report",
        "arguments": {"report_type": "root_cause"},
        "reason": "Save structured RCA",
    })
    return {
        "ok": True,
        "message": "Investigation replay",
        "trace_name": str(trace_name or ""),
        "scope": str(scope or ""),
        "finding": {
            "id": (finding or {}).get("id"),
            "title": (finding or {}).get("title"),
            "severity": (finding or {}).get("severity"),
        } if finding else None,
        "steps": steps,
        "tools_run": tools_run,
        "queries": [dict(q) for q in (queries or []) if isinstance(q, dict)],
        "evidence": [dict(e) for e in (evidence or []) if isinstance(e, dict)],
        "conclusion": str(conclusion or "").strip(),
        "confidence": str(confidence or "").strip(),
        "alternatives": [dict(a) for a in (alternatives or []) if isinstance(a, dict)],
        "evidence_times": times[:20],
        "timestamp": str(timestamp or "").strip(),
        "suggested_tools": suggested,
    }


def build_investigation_package(
    *,
    trace_name: str = "",
    scope: str = "",
    finding: Optional[dict] = None,
    plan: Optional[Dict[str, Any]] = None,
    tools_run: Optional[Sequence[str]] = None,
    queries: Optional[Sequence[Dict[str, Any]]] = None,
    evidence: Optional[Sequence[Dict[str, Any]]] = None,
    conclusion: str = "",
    confidence: str = "",
    alternatives: Optional[Sequence[Dict[str, Any]]] = None,
    evidence_times: Optional[Sequence[float]] = None,
    timestamp: str = "",
) -> Dict[str, Any]:
    """Full JSON-serialisable investigation replay/export package.

    Thin wrapper over ``build_investigation_replay`` that adds a schema /
    version envelope for ``export_investigation`` / ``export_report``
    (format=json).
    """
    package = dict(build_investigation_replay(
        finding=finding,
        plan=plan,
        tools_run=tools_run,
        conclusion=conclusion,
        evidence_times=evidence_times,
        trace_name=trace_name,
        scope=scope,
        queries=queries,
        evidence=evidence,
        confidence=confidence,
        alternatives=alternatives,
        timestamp=timestamp,
    ))
    package["schema"] = "btf-investigation-package"
    package["version"] = 1
    return package


def estimate_what_if(
    *,
    change: str,
    task: str = "",
    findings: Optional[Sequence[dict]] = None,
    baseline_metrics: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Labelled what-if estimate (not a deterministic scheduler simulation)."""
    change = str(change or "").strip()
    task = str(task or "").strip()
    blob = f"{change} {task}".lower()
    findings = list(findings or [])
    focus = resolve_finding(enrich_findings_with_ids(findings), "") if findings else None
    effect = "≈"
    reason = "Insufficient correlated evidence for a directional estimate"
    confidence = "Low"
    if "pin" in blob or "affin" in blob or "core" in blob:
        effect = "↓ migrations / cache miss risk"
        reason = "Affinity reduces cross-core bounce when thrashing dominates"
        confidence = "Medium"
    elif "priorit" in blob:
        effect = "↓ blocking wait for higher-priority waiter (risk: starve lower)"
        reason = "Priority changes alter preemption and inherit geometry"
        confidence = "Medium"
    elif "mutex" in blob or "lock" in blob or "contention" in blob:
        effect = "↓ blocking Max / response"
        reason = "Shorter hold times cut waiters' off-CPU gaps"
        confidence = "Medium"
    elif "migrat" in blob:
        effect = "↓ migration rate; ≈ WCET if CPU-bound"
        reason = "Migration cost is overhead, not always payload"
        confidence = "Medium"
    return {
        "ok": True,
        "message": "What-if estimate (not measured)",
        "disclaimer": "Simulation / estimate — not measured behavior",
        "change": change,
        "task": task,
        "estimated_effect": effect,
        "reason": reason,
        "confidence": confidence,
        "evidence_quality": "Possible explanation",
        "related_finding": (focus or {}).get("id") if focus else None,
        "baseline_metrics": baseline_metrics or {},
        "suggested_tools": [
            {"name": "optimize", "arguments": {}, "reason": "Evidence-backed mitigations"},
            {"name": "correlate_events", "arguments": {"task": task} if task else {},
             "reason": "Verify correlated window"},
        ],
    }


def analyze_multi_traces(
    snapshots: Sequence[Dict[str, Any]],
) -> Dict[str, Any]:
    """Rank multiple trace snapshots (best scheduling behavior first)."""
    rows = []
    for snap in snapshots or []:
        if not isinstance(snap, dict):
            continue
        name = str(snap.get("name") or snap.get("label") or f"trace{len(rows)}")
        metrics = snap.get("metrics") if isinstance(snap.get("metrics"), dict) else snap
        mig = metrics.get("migrations")
        score = metrics.get("load_balance_score")
        missed = metrics.get("missed_ticks")
        # Higher score is better; lower migrations/missed is better.
        rank_key = (
            -(float(score) if score is not None else 0.0),
            float(mig) if mig is not None else 0.0,
            float(missed) if missed is not None else 0.0,
        )
        rows.append({
            "name": name,
            "metrics": {
                "migrations": mig,
                "load_balance_score": score,
                "missed_ticks": missed,
                "migrated_tasks": metrics.get("migrated_tasks"),
                "context_switches": metrics.get("context_switches"),
            },
            "_key": rank_key,
        })
    rows.sort(key=lambda r: r["_key"])
    for i, r in enumerate(rows, start=1):
        r["rank"] = i
        del r["_key"]
    best = rows[0]["name"] if rows else None
    return {
        "ok": True,
        "message": (
            f"Ranked {len(rows)} trace(s); best≈{best}" if rows else "No traces"
        ),
        "ranking": rows,
        "best": best,
        "suggested_tools": [
            {"name": "compare_performance", "arguments": {},
             "reason": "Pairwise A vs B deltas"},
            {"name": "regression_explain", "arguments": {},
             "reason": "Explain primary regression"},
        ],
    }


# --- Heuristic what-if simulator / optimization experiments ---------------

_CORE_TOKEN_RE = re.compile(
    r"(?:core[_\s-]*)?(\d+)\b|(?:c)(\d+)\b",
    re.IGNORECASE,
)


def _gini_local(values: Sequence[float]) -> float:
    vals = [float(v) for v in values if v is not None]
    n = len(vals)
    if n < 2:
        return 0.0
    total = sum(vals)
    if total <= 0:
        return 0.0
    sorted_v = sorted(vals)
    cumsum = 0.0
    gini_num = 0.0
    for v in sorted_v:
        cumsum += v
        gini_num += cumsum
    gini = (n + 1.0) / n - (2.0 * gini_num) / (n * total)
    return max(0.0, min(1.0, gini))


def _load_balance_score_from_pcts(pcts: Sequence[float]) -> float:
    return max(0.0, 100.0 * (1.0 - _gini_local(pcts)))


def parse_what_if_change(change: str, task: str = "") -> Dict[str, Any]:
    """Parse a natural-language change into a structured action."""
    text = str(change or "").strip()
    blob = text.lower()
    task = str(task or "").strip()
    action = {"kind": "unknown", "task": task, "raw": text}
    # pin / affinity to core
    if any(k in blob for k in ("pin", "affin", "bind", "stick")):
        action["kind"] = "pin"
        m = _CORE_TOKEN_RE.search(blob)
        if m:
            action["core"] = int(m.group(1) or m.group(2))
        else:
            action["core"] = None  # choose later from slices
    elif "priorit" in blob:
        action["kind"] = "priority"
        action["direction"] = "up" if any(
            w in blob for w in ("raise", "increase", "higher", "boost", "up")
        ) else ("down" if any(
            w in blob for w in ("lower", "decrease", "reduce", "down")
        ) else "up")
    elif any(k in blob for k in ("mutex", "lock", "contention", "critical")):
        action["kind"] = "reduce_contention"
        # default 50% reduction of blocking attributed to contention
        action["factor"] = 0.5
        m = re.search(r"(\d+(?:\.\d+)?)\s*%", blob)
        if m:
            action["factor"] = max(0.05, min(0.95, float(m.group(1)) / 100.0))
    elif "migrat" in blob:
        action["kind"] = "reduce_migration"
        action["factor"] = 0.5
    return action


def _dominant_core_from_slices(slices: Sequence[dict]) -> Optional[int]:
    by_core: Dict[str, float] = {}
    for sl in slices or []:
        core = str(sl.get("core") or "").strip()
        if not core:
            continue
        try:
            dur = float(sl.get("duration") or 0)
        except (TypeError, ValueError):
            dur = 0.0
        by_core[core] = by_core.get(core, 0.0) + max(0.0, dur)
    if not by_core:
        return None
    best = max(by_core.items(), key=lambda kv: kv[1])[0]
    m = re.search(r"(\d+)", best)
    return int(m.group(1)) if m else None


def _quietest_core(core_utils: Sequence[Any]) -> Optional[int]:
    best_core = None
    best_pct = None
    for row in core_utils or []:
        if isinstance(row, (list, tuple)) and len(row) >= 2:
            name, pct = row[0], row[1]
        elif isinstance(row, dict):
            name, pct = row.get("core") or row.get("name"), row.get("pct") or row.get("util")
        else:
            continue
        try:
            p = float(pct)
        except (TypeError, ValueError):
            continue
        m = re.search(r"(\d+)", str(name))
        if not m:
            continue
        c = int(m.group(1))
        if best_pct is None or p < best_pct:
            best_pct = p
            best_core = c
    return best_core


def _core_util_map(core_utils: Sequence[Any]) -> Dict[int, float]:
    out: Dict[int, float] = {}
    for row in core_utils or []:
        if isinstance(row, (list, tuple)) and len(row) >= 2:
            name, pct = row[0], row[1]
        elif isinstance(row, dict):
            name, pct = row.get("core") or row.get("name"), row.get("pct") or row.get("util")
        else:
            continue
        m = re.search(r"(\d+)", str(name))
        if not m:
            continue
        try:
            out[int(m.group(1))] = float(pct)
        except (TypeError, ValueError):
            continue
    return out


def simulate_what_if(
    *,
    change: str,
    task: str = "",
    slices: Optional[Sequence[dict]] = None,
    migrations: Optional[Sequence[dict]] = None,
    blocking_gaps: Optional[Sequence[dict]] = None,
    core_utils: Optional[Sequence[Any]] = None,
    findings: Optional[Sequence[dict]] = None,
) -> Dict[str, Any]:
    """Heuristic replay of a change against measured slices (not an RTOS kernel).

    Uses measured execution durations and migration counts; reallocates task CPU
    when pinning and scales blocking for contention/priority experiments.
    """
    slices = list(slices or [])
    migrations = list(migrations or [])
    gaps = list(blocking_gaps or [])
    action = parse_what_if_change(change, task)
    task = action.get("task") or task

    base_mig = len(migrations)
    base_block = 0.0
    for g in gaps:
        try:
            base_block += float(g.get("gap") if g.get("gap") is not None else g.get("duration") or 0)
        except (TypeError, ValueError):
            pass
    util_map = _core_util_map(core_utils or [])
    base_pcts = list(util_map.values()) or [0.0]
    base_lb = _load_balance_score_from_pcts(base_pcts)

    # Task CPU ns from slices
    task_ns = 0.0
    for sl in slices:
        try:
            task_ns += float(sl.get("duration") or 0)
        except (TypeError, ValueError):
            pass

    sim_mig = base_mig
    sim_block = base_block
    sim_util = dict(util_map)
    notes = []
    confidence = "Low"
    kind = action.get("kind")

    if kind == "pin":
        core = action.get("core")
        if core is None:
            core = _dominant_core_from_slices(slices)
        if core is None:
            core = _quietest_core(core_utils or [])
        action["core"] = core
        if core is not None:
            # Eliminate migrations for this task (pinned)
            sim_mig = 0
            # Move all task CPU onto pin core for util estimate
            # Remove task share from other cores (approximate by current slice cores)
            by_core_ns: Dict[int, float] = {}
            for sl in slices:
                m = re.search(r"(\d+)", str(sl.get("core") or ""))
                if not m:
                    continue
                c = int(m.group(1))
                try:
                    by_core_ns[c] = by_core_ns.get(c, 0.0) + float(sl.get("duration") or 0)
                except (TypeError, ValueError):
                    pass
            # Relative util shift: convert ns share to % points proportional to task_ns
            if task_ns > 0 and sim_util:
                # Estimate task's util % as mean slice contribution; use fraction of total util
                total_util = sum(sim_util.values()) or 1.0
                task_util_est = min(total_util, max(1.0, total_util * 0.05))
                if by_core_ns:
                    # redistribute measured proportions
                    for c, ns in by_core_ns.items():
                        share = task_util_est * (ns / task_ns)
                        if c in sim_util:
                            sim_util[c] = max(0.0, sim_util[c] - share)
                    sim_util[core] = sim_util.get(core, 0.0) + task_util_est
                else:
                    # unknown distribution: add to pin core only
                    sim_util[core] = sim_util.get(core, 0.0) + task_util_est
            notes.append(f"Pinned {task or 'task'} → Core_{core}; migrations set to 0")
            confidence = "Medium" if slices or migrations else "Low"
        else:
            notes.append("Could not resolve target core; falling back to qualitative estimate")
            return estimate_what_if(change=change, task=task, findings=findings)

    elif kind == "reduce_contention":
        factor = float(action.get("factor") or 0.5)
        sim_block = base_block * (1.0 - factor)
        notes.append(f"Scaled blocking by ×{1.0 - factor:.2f} (contention −{factor * 100:.0f}%)")
        confidence = "Medium" if gaps else "Low"

    elif kind == "priority":
        # Soft: assume raising priority cuts blocking ~25%; lowering increases ~15%
        if action.get("direction") == "up":
            sim_block = base_block * 0.75
            notes.append("Raised priority: estimated −25% blocking wait (risk: starve lower)")
        else:
            sim_block = base_block * 1.15
            notes.append("Lowered priority: estimated +15% blocking wait")
        confidence = "Low"

    elif kind == "reduce_migration":
        factor = float(action.get("factor") or 0.5)
        sim_mig = int(round(base_mig * (1.0 - factor)))
        notes.append(f"Migration count scaled by ×{1.0 - factor:.2f}")
        confidence = "Medium" if migrations else "Low"

    else:
        # Fall back to keyword estimate but mark as non-simulated
        fallback = estimate_what_if(change=change, task=task, findings=findings)
        fallback["simulator"] = "none"
        fallback["disclaimer"] = (
            "Heuristic estimate only — no slice replay "
            "(phrase change as pin/affinity/priority/mutex to run simulator)"
        )
        return fallback

    sim_lb = _load_balance_score_from_pcts(list(sim_util.values()) or base_pcts)
    deltas = {
        "migrations": sim_mig - base_mig,
        "blocking_ns": sim_block - base_block,
        "load_balance_score": sim_lb - base_lb,
    }
    cost_base = (
        1.0 * base_mig
        + 0.000001 * base_block
        + 0.5 * max(0.0, 100.0 - base_lb)
    )
    cost_sim = (
        1.0 * sim_mig
        + 0.000001 * sim_block
        + 0.5 * max(0.0, 100.0 - sim_lb)
    )
    return {
        "ok": True,
        "message": "What-if heuristic simulation",
        "disclaimer": "Heuristic simulator — not an RTOS kernel / not measured",
        "simulator": "slice_replay_v1",
        "change": change,
        "task": task,
        "action": action,
        "baseline": {
            "migrations": base_mig,
            "blocking_ns": base_block,
            "load_balance_score": round(base_lb, 2),
            "slices": len(slices),
        },
        "simulated": {
            "migrations": sim_mig,
            "blocking_ns": sim_block,
            "load_balance_score": round(sim_lb, 2),
        },
        "deltas": {
            "migrations": deltas["migrations"],
            "blocking_ns": deltas["blocking_ns"],
            "load_balance_score": round(deltas["load_balance_score"], 2),
            "cost": round(cost_sim - cost_base, 3),
        },
        "cost": {"baseline": round(cost_base, 3), "simulated": round(cost_sim, 3)},
        "notes": notes,
        "confidence": confidence,
        "evidence_quality": "Strong correlation" if confidence == "Medium" else "Possible explanation",
        "estimated_effect": (
            f"Δmig={deltas['migrations']:+d}, "
            f"Δblock_ns={deltas['blocking_ns']:+.0f}, "
            f"ΔLB={deltas['load_balance_score']:+.1f}"
        ),
        "suggested_tools": [
            {"name": "optimize_experiment", "arguments": {"task": task} if task else {},
             "reason": "Try ranked automatic experiments"},
            {"name": "correlate_events", "arguments": {"task": task} if task else {},
             "reason": "Verify on timeline"},
        ],
    }


def propose_optimization_experiments(
    *,
    task: str = "",
    slices: Optional[Sequence[dict]] = None,
    findings: Optional[Sequence[dict]] = None,
    core_utils: Optional[Sequence[Any]] = None,
    limit: int = 5,
) -> List[Dict[str, Any]]:
    """Candidate changes for automatic optimization experiments."""
    limit = max(1, min(12, int(limit or 5)))
    task = str(task or "").strip()
    if not task and findings:
        ranked = detect_anomalies(findings, limit=3)
        for a in ranked.get("anomalies") or []:
            t = a.get("task") or _guess_task_name(str(a.get("text") or ""))
            if t:
                task = t
                break
    candidates: List[Dict[str, Any]] = []
    dom = _dominant_core_from_slices(slices or [])
    quiet = _quietest_core(core_utils or [])
    if task and dom is not None:
        candidates.append({
            "change": f"pin {task} to Core_{dom}",
            "task": task,
            "rationale": "Pin to dominant execution core",
        })
    if task and quiet is not None and quiet != dom:
        candidates.append({
            "change": f"pin {task} to Core_{quiet}",
            "task": task,
            "rationale": "Pin to quietest core for load balance",
        })
    if task:
        candidates.append({
            "change": f"reduce mutex contention 50% for {task}",
            "task": task,
            "rationale": "Shorten critical sections / lock hold time",
        })
        candidates.append({
            "change": f"raise priority of {task}",
            "task": task,
            "rationale": "Reduce blocking wait (risk: starvation)",
        })
        candidates.append({
            "change": f"reduce migrations 50% for {task}",
            "task": task,
            "rationale": "Affinity / migration throttle",
        })
    # From findings text
    for a in (detect_anomalies(findings or [], limit=3).get("anomalies") or []):
        t = a.get("task") or task
        blob = f"{a.get('title')} {a.get('text')}".lower()
        if t and ("thrash" in blob or "migrat" in blob) and dom is not None:
            cand = {
                "change": f"pin {t} to Core_{dom}",
                "task": t,
                "rationale": f"From finding {a.get('id')}",
            }
            if cand not in candidates:
                candidates.append(cand)
    # dedupe by change string
    seen = set()
    out = []
    for c in candidates:
        key = c["change"]
        if key in seen:
            continue
        seen.add(key)
        out.append(c)
        if len(out) >= limit:
            break
    return out


def run_optimization_experiments(
    *,
    task: str = "",
    slices: Optional[Sequence[dict]] = None,
    migrations: Optional[Sequence[dict]] = None,
    blocking_gaps: Optional[Sequence[dict]] = None,
    core_utils: Optional[Sequence[Any]] = None,
    findings: Optional[Sequence[dict]] = None,
    limit: int = 5,
) -> Dict[str, Any]:
    """Run a small set of what-if simulations and rank by cost improvement."""
    cands = propose_optimization_experiments(
        task=task, slices=slices, findings=findings, core_utils=core_utils, limit=limit,
    )
    results = []
    for c in cands:
        sim = simulate_what_if(
            change=c["change"],
            task=c.get("task") or task,
            slices=slices,
            migrations=migrations,
            blocking_gaps=blocking_gaps,
            core_utils=core_utils,
            findings=findings,
        )
        if sim.get("simulator") == "none":
            continue
        delta_cost = (sim.get("deltas") or {}).get("cost")
        results.append({
            "change": c["change"],
            "task": c.get("task") or task,
            "rationale": c.get("rationale"),
            "deltas": sim.get("deltas"),
            "baseline": sim.get("baseline"),
            "simulated": sim.get("simulated"),
            "cost_delta": delta_cost,
            "confidence": sim.get("confidence"),
            "notes": sim.get("notes"),
        })
    results.sort(key=lambda r: (r.get("cost_delta") is None, r.get("cost_delta") or 0.0))
    for i, r in enumerate(results, start=1):
        r["rank"] = i
    best = results[0] if results else None
    return {
        "ok": True,
        "message": (
            f"{len(results)} experiment(s); best={best['change']}" if best
            else "No runnable experiments (need task slices / metrics)"
        ),
        "disclaimer": "Heuristic simulator — not an RTOS kernel / not measured",
        "experiments": results,
        "best": best,
        "suggested_tools": ([
            {"name": "what_if", "arguments": {
                "change": best.get("change") or "",
                "task": best.get("task") or task,
            }, "reason": "Re-run best experiment detail"},
        ] if best else []) + [
            {"name": "bookmark_finding", "arguments": {},
             "reason": "Mark evidence on timeline"},
        ],
    }


# --- Historical baseline learning (lightweight) --------------------------

_BASELINE_METRIC_KEYS: Tuple[str, ...] = (
    "wcet_us", "blocking_us", "migrations", "response_us",
)


def _empty_baseline_profile() -> Dict[str, Any]:
    return {"version": 1, "samples": 0, "tasks": {}}


def update_baseline_profile(
    profile: Optional[Dict[str, Any]],
    snapshot: Dict[str, Any],
) -> Dict[str, Any]:
    """Merge a metrics snapshot into a running-mean/std baseline profile.

    ``snapshot`` is ``{"tasks": {task: {wcet_us?, blocking_us?, migrations?,
    response_us?}}}``. Uses Welford's online algorithm so the profile only
    stores ``n`` / ``mean`` / ``m2`` per task/metric — no raw history.
    """
    if isinstance(profile, dict):
        out = {
            "version": int(profile.get("version") or 1),
            "samples": int(profile.get("samples") or 0),
            "tasks": {
                str(t): {
                    str(k): dict(v) for k, v in (m or {}).items() if isinstance(v, dict)
                }
                for t, m in (profile.get("tasks") or {}).items()
                if isinstance(m, dict)
            },
        }
    else:
        out = _empty_baseline_profile()
    tasks_in = snapshot.get("tasks") if isinstance(snapshot, dict) else None
    if not isinstance(tasks_in, dict) or not tasks_in:
        return out
    for task, metrics in tasks_in.items():
        if not isinstance(metrics, dict):
            continue
        task = str(task).strip()
        if not task:
            continue
        bucket = out["tasks"].setdefault(task, {})
        for key in _BASELINE_METRIC_KEYS:
            val = metrics.get(key)
            if val is None:
                continue
            try:
                x = float(val)
            except (TypeError, ValueError):
                continue
            stat = bucket.setdefault(key, {"n": 0, "mean": 0.0, "m2": 0.0})
            n = int(stat.get("n", 0)) + 1
            mean = float(stat.get("mean", 0.0))
            m2 = float(stat.get("m2", 0.0))
            delta = x - mean
            mean += delta / n
            m2 += delta * (x - mean)
            stat["n"] = n
            stat["mean"] = mean
            stat["m2"] = m2
    out["samples"] = int(out.get("samples", 0)) + 1
    return out


def score_against_baseline(
    profile: Optional[Dict[str, Any]],
    snapshot: Dict[str, Any],
    *,
    z_threshold: float = 2.0,
) -> Dict[str, Any]:
    """Per-task/metric z-scores of *snapshot* vs a baseline profile.

    Flags entries where ``|z| > z_threshold`` (default 2). Tasks/metrics
    without at least 2 baseline samples are reported with ``z=None``.
    """
    z_threshold = float(z_threshold or 2.0)
    tasks_profile = (profile or {}).get("tasks") if isinstance(profile, dict) else {}
    tasks_profile = tasks_profile if isinstance(tasks_profile, dict) else {}
    tasks_in = snapshot.get("tasks") if isinstance(snapshot, dict) else None
    tasks_in = tasks_in if isinstance(tasks_in, dict) else {}
    scores: List[Dict[str, Any]] = []
    flagged: List[Dict[str, Any]] = []
    for task, metrics in tasks_in.items():
        if not isinstance(metrics, dict):
            continue
        task = str(task).strip()
        base_bucket = tasks_profile.get(task)
        base_bucket = base_bucket if isinstance(base_bucket, dict) else {}
        for key in _BASELINE_METRIC_KEYS:
            val = metrics.get(key)
            if val is None:
                continue
            try:
                x = float(val)
            except (TypeError, ValueError):
                continue
            stat = base_bucket.get(key)
            row: Dict[str, Any] = {
                "task": task, "metric": key, "value": x,
                "n": 0, "mean": None, "std": None, "z": None, "flag": False,
            }
            if isinstance(stat, dict) and int(stat.get("n", 0)) >= 2:
                n = int(stat["n"])
                mean = float(stat.get("mean", 0.0))
                variance = float(stat.get("m2", 0.0)) / max(1, n - 1)
                std = variance ** 0.5
                row["n"] = n
                row["mean"] = round(mean, 4)
                row["std"] = round(std, 4)
                if std > 1e-9:
                    z = (x - mean) / std
                    row["z"] = round(z, 3)
                    row["flag"] = abs(z) > z_threshold
                else:
                    row["z"] = 0.0
            scores.append(row)
            if row["flag"]:
                flagged.append(row)
    flagged.sort(key=lambda r: -abs(r.get("z") or 0.0))
    return {
        "ok": True,
        "message": (
            f"{len(scores)} metric score(s); {len(flagged)} flagged "
            f"(|z|>{z_threshold:g})"
        ),
        "scores": scores,
        "flagged": flagged,
        "z_threshold": z_threshold,
        "has_baseline": bool(tasks_profile),
        "suggested_tools": (
            [{"name": "investigate", "arguments": {},
              "reason": "Drill into flagged task"}] if flagged else []
        ),
    }


# --- AI-generated validation experiments ----------------------------------

def recommend_validation_experiments(
    findings: Sequence[dict],
    *,
    finding_id: str = "",
    task: str = "",
    limit: int = 5,
) -> Dict[str, Any]:
    """Suggest simulation / firmware / measurement experiments from findings.

    Heuristics: thrash/migration → pin, mutex/inversion → shorten critical
    section, WCET spike → profile+trim, load imbalance → rebalance,
    deadline/budget → re-check budgets.
    """
    limit = max(1, min(20, int(limit or 5)))
    items = enrich_findings_with_ids(findings)
    focus: Optional[dict] = None
    if finding_id:
        focus = resolve_finding(items, finding_id)
    if focus is None and task:
        want = task.strip().lower()
        for f in items:
            t = str(f.get("task") or _guess_task_name(str(f.get("text") or "")) or "")
            if t and t.lower() == want:
                focus = f
                break
    if focus is not None:
        pool: List[dict] = [focus]
    elif items:
        anomalies = detect_anomalies(items, limit=max(3, limit))
        pool = [
            {
                "id": a.get("id"), "title": a.get("title"), "text": a.get("text"),
                "severity": a.get("severity"), "task": a.get("task"),
            }
            for a in anomalies.get("anomalies") or []
        ]
    else:
        pool = []

    experiments: List[Dict[str, Any]] = []
    seen_titles: set = set()

    def add(title: str, kind: str, steps: Sequence[str], rationale: str, fid: Any) -> None:
        if title in seen_titles:
            return
        seen_titles.add(title)
        experiments.append({
            "title": title,
            "kind": kind,
            "steps": [str(s) for s in steps],
            "rationale": rationale,
            "evidence_finding": fid,
        })

    for f in pool:
        if len(experiments) >= limit:
            break
        title = str(f.get("title") or "")
        text = str(f.get("text") or "")
        blob = f"{title} {text}".lower()
        t = str(f.get("task") or _guess_task_name(text) or task or "").strip()
        fid = f.get("id")
        tname = t or "the hot task"
        if "thrash" in blob or "migrat" in blob or "bounc" in blob:
            add(
                f"Simulate pinning {tname} to its dominant core",
                "simulation",
                [f"what_if(change='pin {tname} to Core_N')",
                 "Compare migrations / load-balance deltas"],
                "Migration/thrash finding suggests core affinity fixes the bounce",
                fid,
            )
            add(
                f"Pin {tname} in firmware (vTaskCoreAffinitySet)",
                "firmware",
                [f"Call vTaskCoreAffinitySet({tname}, mask) at startup / after creation",
                 "Re-run the same workload and re-capture a trace"],
                "Confirms the simulated affinity fix on real hardware",
                fid,
            )
            add(
                f"Measure migration rate for {tname} before/after the affinity fix",
                "measurement",
                ["Capture baseline trace", "Apply the affinity fix",
                 "Capture candidate trace", "Run compare_performance A vs B"],
                "Directly measures whether thrashing is resolved",
                fid,
            )
        elif "block" in blob or "mutex" in blob or "inversion" in blob or "inherit" in blob:
            add(
                f"Simulate reduced lock contention for {tname}",
                "simulation",
                [f"what_if(change='reduce mutex contention 50% for {tname}')",
                 "Compare blocking Max / response deltas"],
                "Blocking/mutex finding suggests shortening the critical section",
                fid,
            )
            add(
                f"Shorten the critical section for {tname} (firmware)",
                "firmware",
                ["Reduce work performed while the mutex is held",
                 "Or switch to a priority-inheritance mutex "
                 "(xSemaphoreCreateMutex, not a binary semaphore)"],
                "Addresses priority inversion / long hold times at the source",
                fid,
            )
            add(
                f"Measure blocking Max for {tname} before/after the fix",
                "measurement",
                ["Capture baseline trace", "Apply the fix",
                 "Capture candidate trace",
                 f"query_raw_metric(task={tname}, metric=blocking) on both"],
                "Confirms blocking wait actually dropped",
                fid,
            )
        elif "wcet" in blob or "spike" in blob or "execution" in blob or "cpu" in blob:
            add(
                f"Profile execution slices for {tname}",
                "measurement",
                [f"query_raw_metric(task={tname}, metric=execution)",
                 "Jump to the Max slice and inspect surrounding events"],
                "WCET/CPU spike finding needs a profiling pass before code changes",
                fid,
            )
            add(
                f"Trim or split the long slice on {tname} (firmware)",
                "firmware",
                ["Break the long critical section / loop into smaller chunks",
                 "Re-measure Max execution after the change"],
                "Directly reduces WCET at the source",
                fid,
            )
        elif "load" in blob or "balance" in blob:
            add(
                "Simulate rebalanced task placement",
                "simulation",
                ["optimize_experiment() to rank candidate placements",
                 "Compare Load Balance Score deltas"],
                "Load-balance finding suggests a placement change",
                fid,
            )
            add(
                "Measure Load Balance Score before/after static affinity",
                "measurement",
                ["Capture baseline trace", "Apply static core assignment",
                 "Capture candidate trace", "Run analyze_traces or compare_performance"],
                "Confirms the placement change improves balance",
                fid,
            )
        elif "deadline" in blob or "budget" in blob:
            add(
                f"Re-check budget compliance for {tname} after a fix",
                "measurement",
                ["check_budget() with the configured WCET/response/deadline budgets"],
                "Deadline/budget finding needs a direct budget re-check",
                fid,
            )
        else:
            add(
                f"Investigate {title or 'this finding'} further",
                "measurement",
                ["investigate(finding_id) for a root-cause chain",
                 "correlate_events for supporting evidence"],
                "No specialised heuristic match — needs more evidence first",
                fid,
            )
    experiments = experiments[:limit]
    return {
        "ok": True,
        "message": f"{len(experiments)} validation experiment(s) suggested",
        "experiments": experiments,
        "disclaimer": (
            "Simulation / estimate — not measured behavior; firmware steps "
            "are suggestions to implement and re-trace, not applied automatically"
        ),
    }
