"""Findings triage queue helpers.

Lockstep with ``web/src/utils/findingsTriage.js``.
"""
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Sequence

from .evidence_strength import evidence_strength_badge, normalize_evidence_strength


SEVERITY_ORDER = {"error": 0, "warning": 1, "info": 2, "ask": 3}

FINDING_CATEGORIES = (
    "migration", "blocking", "deadline", "load", "jitter",
    "execution", "dispatch", "general",
)

# Sort keys for the Analysis Findings Sort control (default = severity).
SORT_SEVERITY = "severity"
SORT_EVIDENCE = "evidence"
SORT_TITLE = "title"
SORT_CATEGORY = "category"
SORT_KEYS = (SORT_SEVERITY, SORT_EVIDENCE, SORT_TITLE, SORT_CATEGORY)
SORT_LABELS = {
    SORT_SEVERITY: "Severity",
    SORT_EVIDENCE: "Evidence strength",
    SORT_TITLE: "Title",
    SORT_CATEGORY: "Category",
}


def finding_category(finding: Dict[str, Any]) -> str:
    blob = f"{finding.get('title') or ''} {finding.get('text') or ''}".lower()
    if "migrat" in blob or "thrash" in blob or "bounce" in blob:
        return "migration"
    if "block" in blob or "mutex" in blob or "wait" in blob:
        return "blocking"
    if "deadline" in blob or "budget" in blob:
        return "deadline"
    if "load" in blob or "balance" in blob or "gini" in blob:
        return "load"
    if "jitter" in blob or "period" in blob:
        return "jitter"
    if "wcet" in blob or "execution" in blob or "cpu" in blob:
        return "execution"
    if "dispatch" in blob or "latency" in blob:
        return "dispatch"
    return "general"


def finding_evidence_strength(finding: Dict[str, Any]) -> str:
    ev = finding.get("evidence") or []
    if any(isinstance(e, dict) and e.get("time") is not None for e in ev):
        return "direct"
    if ev:
        return "derived"
    return "estimated"


def enrich_finding_card(finding: Dict[str, Any]) -> Dict[str, Any]:
    """Observation / Evidence / Why / Check next card structure."""
    title = str(finding.get("title") or "Finding")
    text = str(finding.get("text") or "")
    strength = finding_evidence_strength(finding)
    badge = evidence_strength_badge(strength)
    ev_lines: List[str] = []
    for ev in finding.get("evidence") or []:
        if not isinstance(ev, dict):
            continue
        label = str(ev.get("label") or ev.get("text") or "evidence")
        t = ev.get("time")
        ev_lines.append(f"{label}: jump:{t}" if t is not None else label)
    return {
        **finding,
        "category": finding_category(finding),
        "evidence_strength": strength,
        "evidence_strength_label": badge["label"],
        "observation": title,
        "evidence_text": "; ".join(ev_lines) if ev_lines else "No timed evidence yet.",
        "why_it_matters": text or "May indicate a timing or scheduling problem in the current Scope.",
        "check_next": finding.get("check_next") or _default_check_next(finding),
    }


def _default_check_next(finding: Dict[str, Any]) -> str:
    cat = finding_category(finding)
    mapping = {
        "migration": "Open Core Migrations and check load balance first.",
        "blocking": "Inspect Blocking Time and Mutex Blocking around the cited time.",
        "deadline": "Open Deadline / CPU Budget and Response Time.",
        "load": "Open Load Balance and Task × Core.",
        "jitter": "Open Period / Jitter and Recurring Patterns.",
        "execution": "Open Execution and Worst Events for Max/outliers.",
        "dispatch": "Open Dispatch latency and Execution.",
    }
    return mapping.get(cat, "Open Statistics for the related metric and verify on the timeline.")


def sort_findings_triage(
    items: Sequence[Dict[str, Any]],
    *,
    sort_by: str = SORT_SEVERITY,
) -> List[Dict[str, Any]]:
    mode = str(sort_by or SORT_SEVERITY).strip().lower()
    if mode not in SORT_KEYS:
        mode = SORT_SEVERITY
    strength_rank = {"direct": 0, "derived": 1, "estimated": 2, "configured": 1}

    def key(f: Dict[str, Any]) -> tuple:
        sev = SEVERITY_ORDER.get(str(f.get("severity") or "info").lower(), 9)
        strength = normalize_evidence_strength(
            f.get("evidence_strength") or finding_evidence_strength(f))
        erank = strength_rank.get(strength, 3)
        title = str(f.get("title") or "")
        cat = str(f.get("category") or finding_category(f))
        if mode == SORT_EVIDENCE:
            return (erank, sev, title)
        if mode == SORT_TITLE:
            return (title.lower(), sev, erank)
        if mode == SORT_CATEGORY:
            return (cat.lower(), sev, erank, title)
        return (sev, erank, title)

    return sorted(
        [enrich_finding_card(dict(f)) for f in items if isinstance(f, dict)],
        key=key,
    )


def filter_findings_triage(
    items: Sequence[Dict[str, Any]],
    *,
    severity: str = "",
    category: str = "",
    task: str = "",
    core: str = "",
    evidence_strength: str = "",
    sort_by: str = SORT_SEVERITY,
) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    sev_w = str(severity or "").strip().lower()
    cat_w = str(category or "").strip().lower()
    task_w = str(task or "").strip().lower()
    core_w = str(core or "").strip().lower()
    ev_w = str(evidence_strength or "").strip().lower()
    for f in sort_findings_triage(items, sort_by=sort_by):
        if sev_w and str(f.get("severity") or "").lower() != sev_w:
            continue
        if cat_w and str(f.get("category") or "").lower() != cat_w:
            continue
        blob = (
            f"{f.get('title') or ''} {f.get('text') or ''} "
            f"{f.get('task') or ''} {f.get('core') or ''}"
        ).lower()
        if task_w and task_w not in blob:
            continue
        if core_w and core_w not in blob:
            continue
        if ev_w and normalize_evidence_strength(f.get("evidence_strength")) != ev_w:
            continue
        out.append(f)
    return out


def finding_filter_facets(items: Sequence[Dict[str, Any]]) -> Dict[str, List[str]]:
    """Distinct category / task / core values for filter controls."""
    cats: set = set()
    tasks: set = set()
    cores: set = set()
    for f in sort_findings_triage(items or []):
        cats.add(str(f.get("category") or "general"))
        task = str(f.get("task") or "").strip()
        if task:
            tasks.add(task)
        core = str(f.get("core") or "").strip()
        if core:
            cores.add(core)
        # Also scrape Core_N from text when no explicit field.
        blob = f"{f.get('title') or ''} {f.get('text') or ''}"
        for m in re.finditer(r"\bCore[_ ]?\d+\b", blob, re.I):
            cores.add(m.group(0).replace(" ", "_"))
    return {
        "categories": sorted(cats),
        "tasks": sorted(tasks, key=str.lower),
        "cores": sorted(cores, key=str.lower),
    }


def group_findings_by_incident(
    items: Sequence[Dict[str, Any]],
    clusters: Optional[Sequence[Dict[str, Any]]] = None,
    *,
    group: bool = True,
) -> List[Dict[str, Any]]:
    """Flat list of display rows: header rows + finding rows.

    Each row is ``{"kind": "header"|"finding", ...}``. Findings keep their
    fields; headers carry ``incident_id``, ``label``, ``count``.
    """
    findings = [f for f in (items or []) if isinstance(f, dict)]
    if not group or not findings:
        return [{"kind": "finding", **f} for f in findings]
    incs = [c for c in (clusters or []) if isinstance(c, dict)]
    id_to_inc: Dict[str, Dict[str, Any]] = {}
    title_to_inc: Dict[str, Dict[str, Any]] = {}
    for inc in incs:
        for fid in inc.get("finding_ids") or []:
            if fid:
                id_to_inc[str(fid)] = inc
        for title in inc.get("findings") or []:
            if title:
                title_to_inc[str(title)] = inc
    buckets: Dict[str, List[Dict[str, Any]]] = {}
    order: List[str] = []
    ungrouped: List[Dict[str, Any]] = []
    for f in findings:
        fid = str(f.get("id") or "")
        title = str(f.get("title") or f.get("observation") or "")
        inc = id_to_inc.get(fid) or title_to_inc.get(title)
        if not inc or int(inc.get("count") or 0) < 2:
            ungrouped.append(f)
            continue
        cid = str(inc.get("id") or "")
        if cid not in buckets:
            buckets[cid] = []
            order.append(cid)
        buckets[cid].append(f)
    rows: List[Dict[str, Any]] = []
    for cid in order:
        members = buckets.get(cid) or []
        if len(members) < 2:
            rows.extend({"kind": "finding", **m} for m in members)
            continue
        inc = id_to_inc.get(str(members[0].get("id") or "")) or {}
        root = str(inc.get("root_suspect") or "mixed")
        rows.append({
            "kind": "header",
            "incident_id": cid,
            "label": f"{cid} · {root}",
            "count": len(members),
            "finding_ids": [str(m.get("id") or "") for m in members],
        })
        for m in members:
            rows.append({"kind": "finding", "incident_id": cid, **m})
    rows.extend({"kind": "finding", **f} for f in ungrouped)
    return rows


def format_investigate_preview(
    finding: Optional[Dict[str, Any]] = None,
    *,
    scope: Optional[Dict[str, Any]] = None,
    section_id: str = "",
    section_label: str = "",
    current_limit: bool = False,
    current_lo: Optional[float] = None,
    current_hi: Optional[float] = None,
) -> str:
    """Human-readable preview of what Investigate will change."""
    if not isinstance(finding, dict):
        return "Select a finding to preview Investigate."
    lines = ["Investigate will:"]
    sid = str(section_id or "").strip()
    slabel = str(section_label or sid or "related Statistics").strip()
    lines.append(f"  • Open Statistics → {slabel}")
    if isinstance(scope, dict) and scope.get("lo") is not None and scope.get("hi") is not None:
        lo = int(scope["lo"])
        hi = int(scope["hi"])
        reason = str(scope.get("reason") or "recommended evidence window").strip()
        lines.append(f"  • Place C1–C2 at {lo}–{hi} ({reason})")
        lines.append("  • Enable Limit to C1–Cn for Statistics / Findings")
        if current_limit and current_lo is not None and current_hi is not None:
            lines.append(
                f"  • Replaces current Scope {int(current_lo)}–{int(current_hi)}"
            )
        elif current_limit:
            lines.append("  • Replaces the current cursor Scope")
        else:
            lines.append("  • Scope is currently Full Trace (Limit off)")
    else:
        lines.append("  • Keep the current cursor Scope (no recommended window)")
    lines.append("You can Undo the Scope change after Confirm.")
    return "\n".join(lines)


# Queue labels shown in the Analysis Findings strip (Done = reviewed).
QUEUE_OPEN = "open"
QUEUE_DONE = "done"
QUEUE_CASE = "case"
QUEUE_DISMISSED = "dismissed"
QUEUE_IDS = (QUEUE_OPEN, QUEUE_DONE, QUEUE_CASE, QUEUE_DISMISSED)


def default_triage_state() -> Dict[str, Any]:
    return {"reviewed": [], "dismissed": {}, "case": []}


def normalize_triage_state(state: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    base = default_triage_state()
    if not isinstance(state, dict):
        return base
    reviewed = [str(x).strip() for x in (state.get("reviewed") or []) if str(x).strip()]
    case = [str(x).strip() for x in (state.get("case") or []) if str(x).strip()]
    dismissed_raw = state.get("dismissed") or {}
    dismissed: Dict[str, str] = {}
    if isinstance(dismissed_raw, dict):
        for k, v in dismissed_raw.items():
            kid = str(k).strip()
            if kid:
                dismissed[kid] = str(v or "Dismissed")
    return {"reviewed": reviewed, "dismissed": dismissed, "case": case}


def finding_queue_status(
    finding_id: str,
    state: Optional[Dict[str, Any]] = None,
) -> str:
    """Primary queue for a finding: dismissed > case > done > open."""
    st = normalize_triage_state(state)
    fid = str(finding_id or "").strip()
    if not fid:
        return QUEUE_OPEN
    if fid in (st.get("dismissed") or {}):
        return QUEUE_DISMISSED
    if fid in (st.get("case") or []):
        return QUEUE_CASE
    if fid in (st.get("reviewed") or []):
        return QUEUE_DONE
    return QUEUE_OPEN


def filter_by_queue(
    items: Sequence[Dict[str, Any]],
    state: Optional[Dict[str, Any]] = None,
    *,
    queue: str = QUEUE_OPEN,
) -> List[Dict[str, Any]]:
    q = str(queue or QUEUE_OPEN).strip().lower() or QUEUE_OPEN
    if q not in QUEUE_IDS:
        q = QUEUE_OPEN
    st = normalize_triage_state(state)
    out: List[Dict[str, Any]] = []
    for f in items:
        if not isinstance(f, dict):
            continue
        if finding_queue_status(str(f.get("id") or ""), st) == q:
            out.append(f)
    return out


def queue_counts(
    items: Sequence[Dict[str, Any]],
    state: Optional[Dict[str, Any]] = None,
) -> Dict[str, int]:
    st = normalize_triage_state(state)
    counts = {qid: 0 for qid in QUEUE_IDS}
    for f in items:
        if not isinstance(f, dict):
            continue
        fid = str(f.get("id") or "").strip()
        if not fid:
            # Findings without ids stay in Open so they remain reachable.
            counts[QUEUE_OPEN] += 1
            continue
        counts[finding_queue_status(fid, st)] += 1
    return counts


def apply_triage_action(
    state: Optional[Dict[str, Any]],
    finding_id: str,
    action: str,
    *,
    reason: str = "",
) -> Dict[str, Any]:
    out = normalize_triage_state(state)
    fid = str(finding_id or "").strip()
    act = str(action or "").strip().lower()
    if not fid:
        return out
    if act in ("reviewed", "done"):
        reviewed = list(out.get("reviewed") or [])
        if fid not in reviewed:
            reviewed.append(fid)
        out["reviewed"] = reviewed
        # Leaving dismissed when marking Done keeps the queue unambiguous.
        dismissed = dict(out.get("dismissed") or {})
        dismissed.pop(fid, None)
        out["dismissed"] = dismissed
    elif act in ("unreviewed", "undo_done"):
        out["reviewed"] = [x for x in (out.get("reviewed") or []) if x != fid]
    elif act == "dismiss":
        dismissed = dict(out.get("dismissed") or {})
        dismissed[fid] = str(reason or "Dismissed")
        out["dismissed"] = dismissed
        out["reviewed"] = [x for x in (out.get("reviewed") or []) if x != fid]
        out["case"] = [x for x in (out.get("case") or []) if x != fid]
    elif act in ("undismiss", "restore"):
        dismissed = dict(out.get("dismissed") or {})
        dismissed.pop(fid, None)
        out["dismissed"] = dismissed
    elif act == "case":
        case = list(out.get("case") or [])
        if fid not in case:
            case.append(fid)
        out["case"] = case
        dismissed = dict(out.get("dismissed") or {})
        dismissed.pop(fid, None)
        out["dismissed"] = dismissed
    elif act == "uncase":
        out["case"] = [x for x in (out.get("case") or []) if x != fid]
    return out


def format_triage_audit_text(
    findings: Sequence[Dict[str, Any]],
    state: Optional[Dict[str, Any]] = None,
) -> str:
    """Append Done / Case / Dismissed sections for Save as text."""
    st = normalize_triage_state(state)
    by_id = {
        str(f.get("id") or "").strip(): f
        for f in findings
        if isinstance(f, dict) and str(f.get("id") or "").strip()
    }
    lines: List[str] = []

    def _title(fid: str) -> str:
        f = by_id.get(fid) or {}
        return str(f.get("title") or fid)

    done = list(st.get("reviewed") or [])
    case = list(st.get("case") or [])
    dismissed = dict(st.get("dismissed") or {})
    if done:
        lines.append("Done:")
        for fid in done:
            lines.append(f"  - {_title(fid)} (id={fid})")
        lines.append("")
    if case:
        lines.append("In case:")
        for fid in case:
            lines.append(f"  - {_title(fid)} (id={fid})")
        lines.append("")
    if dismissed:
        lines.append("Dismissed:")
        for fid, reason in dismissed.items():
            lines.append(f"  - {_title(fid)} (id={fid}): {reason}")
        lines.append("")
    return "\n".join(lines).rstrip()
