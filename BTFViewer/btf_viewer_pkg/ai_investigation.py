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
    "query_raw_metric": ("metrics",),
    "search_timeline": ("metrics",),
    "trigger_compare": ("metrics", "related"),
    "set_cursors": ("narrow",),
    "zoom_to_range": ("narrow",),
    "highlight_task": ("related",),
    "open_corridor_inspector": ("related",),
    "add_annotation": ("validate",),
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
    graph = {
        "finding": {
            "id": focus.get("id"),
            "severity": sev,
            "title": title,
            "text": text,
            "evidence": list(focus.get("evidence") or []),
            "task": focus.get("task") or "",
        },
        "related_findings": related,
        "hypotheses": hypotheses[: max(1, depth + 1)],
        "suggested_tools": suggested,
        "depth": depth,
        "evidence_chain": format_findings_evidence_chain([focus]),
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
    if depth >= 3:
        add("trigger_compare", {}, "Compare two open tabs if available")
    if depth >= 4:
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
