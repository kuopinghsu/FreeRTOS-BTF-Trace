"""Phase 1–3 investigation planner (Desktop). Keep in sync with web aiPlanner.js."""
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Sequence, Tuple

_TASK_RE = re.compile(r"([A-Za-z_][\w.-]*\s*\[[^\]]+\])")
_PATTERN_KEYS: Tuple[Tuple[str, Tuple[str, ...]], ...] = (
    ("migration", ("migrat", "thrash", "bounce", "ping-pong")),
    ("mutex", ("mutex", "lock", "contention", "sync")),
    ("blocking", ("block", "wait", "hold")),
    ("deadline", ("deadline", "miss", "late")),
    ("load", ("imbalance", "load", "util")),
    ("inversion", ("inversion", "inherit", "boost")),
    ("preemption", ("preempt", "interrupt")),
    ("wcet", ("wcet", "execution", "runtime")),
    ("tick", ("tick", "tickless")),
)

_OUTCOMES: List[Dict[str, Any]] = []


def experiment_outcomes() -> List[Dict[str, Any]]:
    return list(_OUTCOMES)


def set_experiment_outcomes(rows: Optional[Sequence[dict]] = None) -> None:
    _OUTCOMES.clear()
    for row in rows or []:
        if isinstance(row, dict):
            _OUTCOMES.append(dict(row))


def _blob(finding: dict) -> str:
    return f"{finding.get('title') or ''} {finding.get('text') or ''}".lower()


def _task_of(finding: dict) -> str:
    t = str(finding.get("task") or "").strip()
    if t:
        return t
    m = _TASK_RE.search(str(finding.get("text") or finding.get("title") or ""))
    return m.group(1).replace(" ", "") if m else ""


def _patterns(text: str) -> List[str]:
    blob = str(text or "").lower()
    return [name for name, keys in _PATTERN_KEYS if any(k in blob for k in keys)]


def _band(count: int, high: int = 3, mid: int = 1) -> str:
    if count >= high:
        return "HIGH"
    if count >= mid:
        return "MEDIUM"
    return "LOW"


def _items(findings: Optional[Sequence[dict]]) -> List[dict]:
    return [f for f in (findings or []) if isinstance(f, dict)]


def score_hypotheses(
    hypotheses: Optional[Sequence[dict]] = None,
    *,
    findings: Optional[Sequence[dict]] = None,
    contradictions: Optional[Sequence[dict]] = None,
) -> List[Dict[str, Any]]:
    """Evidence-weighted hypothesis scores (0–1)."""
    items = _items(findings)
    contradicted = {
        str(c.get("hypothesis_id") or c.get("hypothesis") or "").lower()
        for c in (contradictions or [])
        if isinstance(c, dict) and str(c.get("verdict") or "").upper() == "CONTRADICTED"
    }
    pool_pat = []
    for f in items:
        pool_pat.extend(_patterns(_blob(f)))
    out: List[Dict[str, Any]] = []
    raw = [h for h in (hypotheses or []) if isinstance(h, dict)]
    n = max(len(raw), 1)
    for i, h in enumerate(raw):
        hyp = str(h.get("hypothesis") or h.get("description") or "").strip()
        hid = str(h.get("id") or f"H{i + 1}")
        prior = 0.55 if i == 0 else max(0.08, 0.35 / i)
        pats = _patterns(hyp + " " + str(h.get("why") or ""))
        overlap = sum(1 for p in pats if p in pool_pat)
        ev_w = min(0.35, 0.12 * overlap)
        status = str(h.get("status") or "").lower()
        if status == "supported":
            ev_w += 0.2
        elif status == "rejected":
            ev_w -= 0.35
        elif status == "need_evidence":
            ev_w -= 0.05
        if hid.lower() in contradicted or hyp.lower() in contradicted:
            ev_w -= 0.4
        score = max(0.02, min(0.97, prior + ev_w))
        out.append({
            **h,
            "id": hid,
            "hypothesis": hyp or hid,
            "prior": round(prior, 3),
            "score": round(score, 3),
        })
    total = sum(float(h["score"]) for h in out) or 1.0
    for h in out:
        h["score"] = round(float(h["score"]) / total, 3)
    out.sort(key=lambda r: -float(r.get("score") or 0))
    return out


def plan_investigation(
    findings: Optional[Sequence[dict]] = None,
    *,
    question: str = "",
    finding_id: str = "",
) -> Dict[str, Any]:
    items = _items(findings)
    focus = items[0] if items else {}
    if finding_id:
        want = finding_id.lower()
        for f in items:
            if want in str(f.get("id") or "").lower() or want in str(f.get("title") or "").lower():
                focus = f
                break
    task = _task_of(focus)
    pats = _patterns(_blob(focus) + " " + question)
    hyps = []
    labels = {
        "migration": "Migration thrashing",
        "mutex": "Mutex contention",
        "inversion": "Priority inversion",
        "deadline": "Deadline miss from execution inflation",
        "load": "Load imbalance",
        "blocking": "Blocking / wait",
        "preemption": "Preemption burst",
        "wcet": "WCET pressure",
    }
    seen = set()
    for p in pats or ["migration"]:
        if p in seen:
            continue
        seen.add(p)
        hyps.append({"id": f"H{len(hyps) + 1}", "hypothesis": labels.get(p, p), "why": p})
    if not hyps:
        hyps = [{"id": "H1", "hypothesis": "Primary finding", "why": "top finding"}]
    scored = score_hypotheses(hyps, findings=items)
    steps = ["cluster_findings", "detect_anomalies"]
    if "migration" in pats:
        steps += ["query_raw_metric:migrations", "correlate_events"]
    if "mutex" in pats or "blocking" in pats:
        steps += ["query_raw_metric:blocking", "detect_priority_inversion"]
    if "deadline" in pats or "wcet" in pats:
        steps += ["query_raw_metric:execution", "find_critical_path"]
    steps += ["detect_contradictions", "assess_evidence_sufficiency"]
    # unique preserve order
    uniq = []
    for s in steps:
        if s not in uniq:
            uniq.append(s)
    times = []
    for ev in focus.get("evidence") or []:
        if isinstance(ev, dict) and ev.get("time") is not None:
            times.append(ev.get("time"))
    scope = {
        "tasks": [task] if task else [],
        "time": [times[0], times[-1]] if len(times) >= 2 else times[:1],
        "patterns": pats,
        "finding_id": focus.get("id") or finding_id,
    }
    return {
        "ok": True,
        "message": f"Plan with {len(scored)} hypotheses, {len(uniq)} steps",
        "scope": scope,
        "hypotheses": scored,
        "steps": uniq,
        "question": str(question or ""),
    }


def suggest_scope(
    question: str = "",
    findings: Optional[Sequence[dict]] = None,
    *,
    cursor_lo: Optional[float] = None,
    cursor_hi: Optional[float] = None,
) -> Dict[str, Any]:
    items = _items(findings)
    q = str(question or "").strip()
    focus = items[0] if items else {}
    qlow = q.lower()
    for f in items:
        blob = _blob(f)
        if any(tok in blob for tok in qlow.split() if len(tok) > 3):
            focus = f
            break
        if _task_of(f) and _task_of(f).lower() in qlow:
            focus = f
            break
    task = _task_of(focus)
    related = []
    for f in items:
        t = _task_of(f)
        if t and t != task and t not in related:
            related.append(t)
        if len(related) >= 3:
            break
    times = []
    for ev in focus.get("evidence") or []:
        if isinstance(ev, dict) and ev.get("time") is not None:
            try:
                times.append(float(ev["time"]))
            except (TypeError, ValueError):
                pass
    if cursor_lo is not None and cursor_hi is not None:
        lo, hi = min(cursor_lo, cursor_hi), max(cursor_lo, cursor_hi)
    elif len(times) >= 2:
        lo, hi = min(times), max(times)
    elif times:
        lo = hi = times[0]
    else:
        lo = hi = None
    reason = "Top finding plus evidence times."
    if task and times:
        reason = f"Focus {task}; evidence clustered at {lo}–{hi}."
    elif q:
        reason = f"Interpreted from: {q[:120]}"
    return {
        "ok": True,
        "message": "Recommended investigation scope",
        "task": task,
        "related_tasks": related,
        "time_lo": lo,
        "time_hi": hi,
        "finding_id": focus.get("id"),
        "reason": reason,
        "apply_scope": True,
    }


def detect_contradictions(
    findings: Optional[Sequence[dict]] = None,
    *,
    hypothesis: str = "",
    metrics: Optional[dict] = None,
) -> Dict[str, Any]:
    items = _items(findings)
    hyp = str(hypothesis or "").strip() or (
        str((items[0] or {}).get("title") or "") if items else ""
    )
    blob = hyp.lower()
    metrics = metrics if isinstance(metrics, dict) else {}
    reasons: List[str] = []
    verdict = "INSUFFICIENT"

    def _num(key: str) -> Optional[float]:
        try:
            return float(metrics[key])
        except (KeyError, TypeError, ValueError):
            return None

    blocking = _num("blocking") or _num("blocking_pct")
    execution = _num("execution") or _num("execution_pct")
    mutex = _num("mutex_hold") or _num("hold")
    migrations = _num("migrations")
    if "mutex" in blob or "contention" in blob or "block" in blob:
        if execution is not None and blocking is not None and execution > blocking * 3:
            verdict = "CONTRADICTED"
            reasons.append("Dominant regression is execution, not synchronization.")
        if mutex is not None and abs(mutex) < 1e-6:
            verdict = "CONTRADICTED"
            reasons.append("Mutex hold time unchanged.")
    if "migrat" in blob or "thrash" in blob:
        if migrations is not None and migrations < 1:
            verdict = "CONTRADICTED"
            reasons.append("Migration count is not elevated.")
    titles = " ".join(_blob(f) for f in items)
    if "mutex" in blob and "migrat" in titles and "mutex" not in titles:
        verdict = "CONTRADICTED"
        reasons.append("Findings emphasise migration, not mutex.")
    if not reasons and items:
        verdict = "SUPPORTED" if any(p in titles for p in _patterns(blob)) else "INSUFFICIENT"
        if verdict == "SUPPORTED":
            reasons.append("Finding text overlaps the hypothesis.")
    return {
        "ok": True,
        "message": verdict,
        "hypothesis": hyp,
        "verdict": verdict,
        "reasons": reasons,
        "metrics": metrics,
    }


def assess_evidence_sufficiency(
    findings: Optional[Sequence[dict]] = None,
    *,
    tools_run: Optional[Sequence[str]] = None,
    contradictions: Optional[Sequence[dict]] = None,
    coverage: Optional[dict] = None,
) -> Dict[str, Any]:
    items = _items(findings)
    tools = [str(t) for t in (tools_run or [])]
    cov = coverage if isinstance(coverage, dict) else {}
    pct = cov.get("percent")
    if pct is None:
        pct = min(95, 20 + 15 * min(len(items), 4) + 8 * min(len(tools), 6))
    try:
        pct = int(round(float(pct)))
    except (TypeError, ValueError):
        pct = 0
    contradicted = any(
        str(c.get("verdict") or "").upper() == "CONTRADICTED"
        for c in (contradictions or []) if isinstance(c, dict)
    )
    has_alt = any("mutex" in _blob(f) or "migrat" in _blob(f) for f in items)
    stop = pct >= 80 and len(tools) >= 2 and not contradicted
    rec = "STOP INVESTIGATION" if stop else "CONTINUE"
    if contradicted:
        rec = "REVISE HYPOTHESIS"
    return {
        "ok": True,
        "message": rec,
        "coverage_percent": pct,
        "recommendation": rec,
        "stop": stop,
        "supporting": [str(f.get("title") or f.get("id") or "") for f in items[:6]],
        "tools_run": tools,
        "contradicted": contradicted,
        "alternative_seen": has_alt,
    }


def cluster_findings(findings: Optional[Sequence[dict]] = None) -> Dict[str, Any]:
    items = _items(findings)
    incidents: List[Dict[str, Any]] = []
    used = set()
    for i, f in enumerate(items):
        if i in used:
            continue
        pats = set(_patterns(_blob(f)))
        task = _task_of(f)
        members = [f]
        used.add(i)
        for j, g in enumerate(items):
            if j in used:
                continue
            gp = set(_patterns(_blob(g)))
            gt = _task_of(g)
            if (task and gt == task) or (pats and gp and pats & gp):
                members.append(g)
                used.add(j)
        titles = [str(m.get("title") or m.get("id") or "") for m in members]
        root = _task_of(members[0])
        incidents.append({
            "id": f"I{len(incidents) + 1}",
            "root_suspect": root,
            "patterns": sorted(pats),
            "findings": titles,
            "count": len(members),
        })
    return {
        "ok": True,
        "message": f"{len(incidents)} incident cluster(s) from {len(items)} findings",
        "incidents": incidents,
    }


def generate_fingerprint(
    findings: Optional[Sequence[dict]] = None,
    *,
    metrics: Optional[dict] = None,
) -> Dict[str, Any]:
    items = _items(findings)
    counts: Dict[str, int] = {name: 0 for name, _k in _PATTERN_KEYS}
    for f in items:
        for p in _patterns(_blob(f)):
            counts[p] = counts.get(p, 0) + 1
    metrics = metrics if isinstance(metrics, dict) else {}
    try:
        if float(metrics.get("migrations") or 0) > 20:
            counts["migration"] += 2
    except (TypeError, ValueError):
        pass
    scheduling = {
        "migration": _band(counts.get("migration", 0)),
        "load_balance": _band(counts.get("load", 0)),
        "preemption": _band(counts.get("preemption", 0)),
    }
    sync = {
        "blocking": _band(counts.get("blocking", 0)),
        "mutex_contention": _band(counts.get("mutex", 0)),
        "pi": _band(counts.get("inversion", 0)),
    }
    timing = {
        "wcet_pressure": _band(counts.get("wcet", 0)),
        "deadline_miss": _band(counts.get("deadline", 0)),
    }
    hot = [k for k, v in {**scheduling, **sync, **timing}.items() if v == "HIGH"]
    pattern = " + ".join(hot) if hot else "nominal"
    return {
        "ok": True,
        "message": f"Pattern: {pattern}",
        "scheduling": scheduling,
        "synchronization": sync,
        "timing": timing,
        "pattern": pattern,
        "counts": counts,
    }


def _fp_tags(fp: dict) -> set:
    tags = set()
    for group in ("scheduling", "synchronization", "timing"):
        block = fp.get(group) if isinstance(fp.get(group), dict) else {}
        for k, v in block.items():
            if str(v).upper() in ("HIGH", "MEDIUM"):
                tags.add(k)
    pat = str(fp.get("pattern") or "")
    if pat:
        tags.add(pat.lower())
    return tags


def find_similar_investigations(
    findings: Optional[Sequence[dict]] = None,
    *,
    history: Optional[Sequence[dict]] = None,
    limit: int = 5,
) -> Dict[str, Any]:
    current = generate_fingerprint(findings)
    tags = _fp_tags(current)
    hist = [h for h in (history or []) if isinstance(h, dict)]
    hist = hist + [h for h in _OUTCOMES if isinstance(h, dict)]
    scored: List[Dict[str, Any]] = []
    for i, row in enumerate(hist):
        fp = row.get("fingerprint") if isinstance(row.get("fingerprint"), dict) else row
        other = _fp_tags(fp)
        if not tags and not other:
            sim = 0
        else:
            sim = int(round(100.0 * len(tags & other) / max(len(tags | other), 1)))
        if sim <= 0:
            continue
        scored.append({
            "id": row.get("id") or f"#{i + 1}",
            "similarity": sim,
            "solution": row.get("solution") or row.get("change") or "",
            "result": row.get("result") or row.get("actual") or "",
            "pattern": fp.get("pattern") or row.get("pattern") or "",
        })
    scored.sort(key=lambda r: -int(r.get("similarity") or 0))
    scored = scored[: max(1, min(20, int(limit or 5)))]
    return {
        "ok": True,
        "message": f"{len(scored)} similar investigation(s)",
        "current": current,
        "matches": scored,
    }


def regression_localize(
    candidate: Optional[dict] = None,
    baseline: Optional[dict] = None,
    *,
    findings: Optional[Sequence[dict]] = None,
    label_a: str = "A",
    label_b: str = "B",
) -> Dict[str, Any]:
    cand = candidate if isinstance(candidate, dict) else {}
    base = baseline if isinstance(baseline, dict) else {}
    cm = cand.get("metrics") if isinstance(cand.get("metrics"), dict) else cand
    bm = base.get("metrics") if isinstance(base.get("metrics"), dict) else base
    deltas = {}
    for key in ("execution", "migrations", "preemptions", "blocking", "load_balance_score"):
        try:
            a = float(cm.get(key))
            b = float(bm.get(key))
            deltas[key] = round(a - b, 3)
        except (TypeError, ValueError):
            continue
    items = _items(findings)
    task = _task_of(items[0]) if items else ""
    times = []
    for f in items:
        for ev in f.get("evidence") or []:
            if isinstance(ev, dict) and ev.get("time") is not None:
                times.append(ev.get("time"))
    region = [min(times), max(times)] if times else []
    mech = []
    if deltas.get("migrations", 0) > 0:
        mech.append("migration")
    if deltas.get("preemptions", 0) > 0:
        mech.append("preemption")
    if deltas.get("execution", 0) > 0:
        mech.append("execution inflation")
    return {
        "ok": True,
        "message": f"Localized {label_a} vs {label_b}",
        "overall": deltas,
        "task": task,
        "region": region,
        "likely_mechanism": " → ".join(mech) or "unspecified",
        "primary_change": deltas,
    }


def build_causal_chain(
    findings: Optional[Sequence[dict]] = None,
    *,
    events: Optional[Sequence[dict]] = None,
) -> Dict[str, Any]:
    items = _items(findings)
    pats = []
    for f in items:
        for p in _patterns(_blob(f)):
            if p not in pats:
                pats.append(p)
    order = ["migration", "preemption", "wcet", "blocking", "deadline"]
    nodes = [p for p in order if p in pats]
    if not nodes:
        nodes = pats[:4] or ["finding"]
    edges = []
    for a, b in zip(nodes, nodes[1:]):
        rel = "temporal" if a in ("migration", "preemption") else "correlated"
        if a == "migration" and b in ("preemption", "wcet"):
            rel = "causal"
        edges.append({
            "from": a,
            "to": b,
            "relationship": rel,
            "confidence": "Medium" if rel != "causal" else "Low",
            "evidence": [str(f.get("title") or "") for f in items[:3]],
        })
    lines = ["graph TD"]
    for i, n in enumerate(nodes):
        lines.append(f"N{i}[{n}]")
    for i in range(1, len(nodes)):
        lines.append(f"N{i-1} --> N{i}")
    extra = [e for e in (events or []) if isinstance(e, dict)]
    return {
        "ok": True,
        "message": f"{len(nodes)}-step causal chain",
        "nodes": nodes,
        "edges": edges,
        "mermaid": "\n".join(lines),
        "event_count": len(extra),
        "disclaimer": "correlation should never silently become causation",
    }


def generate_experiment_plan(
    findings: Optional[Sequence[dict]] = None,
    *,
    task: str = "",
    limit: int = 3,
) -> Dict[str, Any]:
    items = _items(findings)
    t = str(task or "").strip() or (_task_of(items[0]) if items else "the hot task")
    blob = " ".join(_blob(f) for f in items)
    plans: List[Dict[str, Any]] = []
    if "migrat" in blob or "thrash" in blob or not blob:
        plans.append({
            "title": f"Pin {t} to Core_0",
            "change": f"pin {t} to Core_0",
            "expected": "migrations -40~60%",
            "risk": "load imbalance",
        })
    if "mutex" in blob or "block" in blob:
        plans.append({
            "title": "Reduce mutex hold time 30%",
            "change": f"reduce mutex contention 30% for {t}",
            "expected": "blocking -25~35%",
            "risk": "throughput on holder",
        })
    if "invert" in blob or "priorit" in blob:
        plans.append({
            "title": f"Raise waiter priority / shorten inherit for {t}",
            "change": f"raise priority of waiter of {t}",
            "expected": "PI duration -20%",
            "risk": "starve lower tasks",
        })
    if "deadline" in blob or "wcet" in blob:
        plans.append({
            "title": f"Trim WCET of {t}",
            "change": f"reduce execution of {t} 20%",
            "expected": "deadline misses down",
            "risk": "feature cut",
        })
    plans = plans[: max(1, min(8, int(limit or 3)))]
    return {
        "ok": True,
        "message": f"{len(plans)} experiment plan(s)",
        "task": t,
        "experiments": plans,
        "actions": ["what_if", "optimize_experiment", "validate_experiment"],
    }


def record_experiment_outcome(
    *,
    change: str = "",
    predicted: str = "",
    actual: str = "",
    quality: str = "",
    fingerprint: Optional[dict] = None,
    findings: Optional[Sequence[dict]] = None,
) -> Dict[str, Any]:
    pred = str(predicted or "")
    act = str(actual or "")
    q = str(quality or "").strip().upper()
    if not q:
        q = "GOOD" if pred and act and pred[:8] == act[:8] else (
            "PARTIAL" if act else "UNKNOWN"
        )
    fp = fingerprint if isinstance(fingerprint, dict) else generate_fingerprint(findings)
    row = {
        "id": f"E{len(_OUTCOMES) + 1}",
        "change": str(change or ""),
        "predicted": pred,
        "actual": act,
        "quality": q,
        "fingerprint": fp,
        "solution": str(change or ""),
        "result": act,
        "confidence_delta": 1 if q == "GOOD" else (-1 if q == "BAD" else 0),
    }
    _OUTCOMES.append(row)
    return {
        "ok": True,
        "message": f"Recorded outcome {row['id']} ({q})",
        "outcome": row,
        "history_size": len(_OUTCOMES),
        "future_recommendation_confidence": "up" if row["confidence_delta"] > 0 else (
            "down" if row["confidence_delta"] < 0 else "unchanged"
        ),
    }


def score_investigation_metrics(
    *,
    expected: Optional[dict] = None,
    actual_conclusion: str = "",
    tools: Optional[Sequence[str]] = None,
    elapsed_s: Optional[float] = None,
    evidence_quality: Optional[dict] = None,
    catalog: Optional[dict] = None,
    passed: bool = True,
    confidence: str = "",
    finding_score: int = 0,
) -> Dict[str, Any]:
    """Phase 3 measurable scores (0–100) for a finished investigation."""
    tools_l = [str(t) for t in (tools or [])]
    n_tools = max(len(tools_l), 1)
    exp = expected if isinstance(expected, dict) else {}
    try:
        fs = int(finding_score)
    except (TypeError, ValueError):
        fs = 0
    evidence_efficiency = int(round(min(100, fs / n_tools * (3 if n_tools <= 3 else 1))))
    lat = 0.0
    if elapsed_s is not None:
        try:
            lat = float(elapsed_s)
        except (TypeError, ValueError):
            lat = 0.0
    # Lower tools+latency is better; map onto 0–100.
    investigation_cost = int(max(0, min(100, 100 - 4 * len(tools_l) - min(40, lat))))
    conf = str(confidence or "").lower()
    band = str((evidence_quality or {}).get("band") or "").lower()
    high_conf = "high" in conf or band in ("strong", "medium-high")
    false_confidence = 0 if (high_conf and not passed) else 100
    falsify_tools = {
        "detect_contradictions", "manage_hypotheses", "assess_evidence_sufficiency",
    }
    falsification_quality = 100 if any(t in falsify_tools for t in tools_l) else (
        60 if "investigate" in tools_l else 30
    )
    cat = catalog if isinstance(catalog, dict) else {}
    want_tasks = [str(x).lower() for x in (exp.get("tasks") or cat.get("tasks") or [])]
    conc = str(actual_conclusion or "").lower()
    if not want_tasks:
        scope_accuracy = 100
    else:
        hits = sum(1 for t in want_tasks if t in conc)
        scope_accuracy = int(round(100.0 * hits / len(want_tasks)))
    stop_efficiency = 100 if "assess_evidence_sufficiency" in tools_l else (
        80 if len(tools_l) <= 6 else max(20, 80 - 8 * (len(tools_l) - 6))
    )
    return {
        "evidence_efficiency": evidence_efficiency,
        "investigation_cost": investigation_cost,
        "false_confidence": false_confidence,
        "falsification_quality": falsification_quality,
        "scope_accuracy": scope_accuracy,
        "stop_efficiency": stop_efficiency,
    }


def score_investigation_tool(
    findings: Optional[Sequence[dict]] = None,
    *,
    tools_run: Optional[Sequence[str]] = None,
    elapsed_s: Optional[float] = None,
    conclusion: str = "",
    confidence: str = "",
) -> Dict[str, Any]:
    metrics = score_investigation_metrics(
        actual_conclusion=conclusion,
        tools=tools_run,
        elapsed_s=elapsed_s,
        passed=True,
        confidence=confidence,
        finding_score=min(100, 20 * len(_items(findings))),
        catalog={"tasks": [_task_of(f) for f in _items(findings) if _task_of(f)]},
    )
    return {
        "ok": True,
        "message": "Investigation scores",
        **metrics,
        "tools_run": list(tools_run or []),
    }
