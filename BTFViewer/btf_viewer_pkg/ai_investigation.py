"""Investigation plan, evidence chain, baselines, and CI regression helpers.

Keep behaviour in sync with ``web/src/utils/aiInvestigation.js``.
"""
from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Optional, Sequence, Tuple

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
}

_AGENT_TEMPLATE_IDS = frozenset({
    "investigate", "root_cause", "what_if", "optimize", "diagnostic_report",
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
        if "evidence" not in item:
            item["evidence"] = list(item.get("evidence") or [])
        out.append(item)
    return out


def format_findings_evidence_chain(findings: Sequence[dict]) -> str:
    """Markdown evidence-chain block for AI context / UI."""
    lines = ["### Evidence chain", ""]
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
            "suggested_tools": [],
            "plan": default_investigation_plan(),
            "evidence_chain": format_findings_evidence_chain([]),
        }

    title = str(focus.get("title") or "")
    text = str(focus.get("text") or "")
    sev = str(focus.get("severity") or "info")
    hypotheses = _hypotheses_for_finding(title, text)
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
    graph = {
        "finding": {
            "id": focus.get("id"),
            "severity": sev,
            "title": title,
            "text": text,
            "evidence": list(focus.get("evidence") or []),
            "task": focus.get("task") or _guess_task_name(text),
        },
        "related_findings": related,
        "hypotheses": hypotheses[: max(1, depth + 1)],
        "suggested_tools": suggested,
        "depth": depth,
        "evidence_chain": format_findings_evidence_chain([focus]),
        "root_cause_chain": chain,
        "ranked_anomalies": (anomalies.get("anomalies") or [])[: max(3, depth)],
        "plan": plan,
    }
    return {
        "ok": True,
        "message": (
            f"Investigation context for {focus.get('id')} "
            f"({len(hypotheses)} hypotheses, {len(suggested)} suggested tools)"
        ),
        **graph,
    }


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


_TASK_TOKEN_RE = re.compile(
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
    for m in _TASK_TOKEN_RE.finditer(text or ""):
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
        })
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
    return {
        "ok": True,
        "message": str(result.get("summary") or "compared"),
        "label_a": label_a,
        "label_b": label_b,
        "failed": bool(result.get("failed")),
        "checks": result.get("checks") or [],
        "primary_regression": primary,
        "confidence": confidence,
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


_REPORT_TYPES = frozenset({
    "executive", "performance", "root_cause", "regression",
    "optimization", "bug", "ci",
})


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
    lines.append("## Key findings")
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
        "## Recommended actions",
        "1. Place cursors / zoom on the worst episode (`set_cursors`, `zoom_to_range`).",
        "2. Highlight the focus task and verify on the timeline.",
        "3. Re-run Trace Compare or `compare_performance` after a fix.",
        "",
        "## Confidence",
        "Medium — structured from Analysis Findings; confirm with tool evidence.",
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
    return {
        "ok": True,
        "message": "Regression explained" if failed else "No regression to explain",
        "failed": failed,
        "markdown": "\n".join(lines),
        "primary_regression": primary,
        "confidence": conf,
        "suggested_tools": [
            {"name": "correlate_events", "arguments": {}, "reason": "Timeline for worst metric"},
            {"name": "investigate", "arguments": {}, "reason": "Root-cause chain"},
        ],
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
) -> Dict[str, Any]:
    """Structured investigation replay card for UI / export."""
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
        "finding": {
            "id": (finding or {}).get("id"),
            "title": (finding or {}).get("title"),
            "severity": (finding or {}).get("severity"),
        } if finding else None,
        "steps": steps,
        "tools_run": tools_run,
        "conclusion": str(conclusion or "").strip(),
        "evidence_times": times[:20],
        "suggested_tools": suggested,
    }


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
    """Heuristic replay of a change against measured slices (not FreeRTOS kernel).

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
        "disclaimer": "Heuristic simulator — not FreeRTOS kernel / not measured",
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
        "disclaimer": "Heuristic simulator — not FreeRTOS kernel / not measured",
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
