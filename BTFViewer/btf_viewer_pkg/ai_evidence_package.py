"""Compact AI evidence package.

Assemble only the evidence needed to answer one question — the user's question
and range, trace-health status + limitations, related entities, the required
statistics with units and sample counts, a short event context around the
range, and the findings / bookmarks the user picked — plus stable identifiers
and an explicit fact / inference / missing-evidence instruction.

Pure and deterministic. ``estimate_tokens`` gives a rough size before anything
is sent; ``format_evidence_package_preview`` renders exactly what would go out.
Keep in sync with ``web/src/utils/aiEvidencePackage.js``.
"""
from __future__ import annotations

import json
from typing import Any, Dict, List, Optional, Sequence

EVIDENCE_PACKAGE_SCHEMA = "btf-viewer-evidence/1"

RESPONSE_CONTRACT = [
    "Confirmed observations",
    "Possible explanations",
    "Contradicting or missing evidence",
    "Recommended verification steps",
    "Evidence references",
]

_INSTRUCTIONS = (
    "Answer only from the evidence below. Separate confirmed observations from "
    "inferences, and name missing evidence explicitly. Every claim must cite an "
    "evidence id or a time/value from this package; mark any uncited statement "
    "as unverified. If the evidence is insufficient, say so."
)


def _redact_name(name: str, redact: bool, alias_map: Dict[str, str]) -> str:
    if not redact or not name:
        return name
    if name not in alias_map:
        alias_map[name] = f"task_{len(alias_map) + 1}"
    return alias_map[name]


def build_evidence_package(
    *,
    question: str,
    scope: str = "",
    analysis_range: Optional[Dict[str, int]] = None,
    trace_name: str = "",
    trace_summary: Optional[Dict[str, Any]] = None,
    health: Optional[Dict[str, Any]] = None,
    findings: Optional[Sequence[Dict[str, Any]]] = None,
    investigation: Optional[Dict[str, Any]] = None,
    entities: Optional[Sequence[str]] = None,
    cores: Optional[Sequence[str]] = None,
    statistics: Optional[Sequence[Dict[str, Any]]] = None,
    event_context: Optional[Sequence[Dict[str, Any]]] = None,
    redact_names: bool = False,
) -> Dict[str, Any]:
    """Build a compact, provider-independent evidence package dict."""
    alias_map: Dict[str, str] = {}

    def red(v: str) -> str:
        return _redact_name(str(v or ""), redact_names, alias_map)

    fnd = []
    for i, f in enumerate(findings or []):
        if not isinstance(f, dict):
            continue
        fnd.append({
            "id": f"F{i + 1}",
            "rule_id": str(f.get("rule_id") or f.get("id") or ""),
            "severity": str(f.get("severity") or "info"),
            "observation": str(f.get("observation") or f.get("title") or f.get("text") or ""),
            "entities": [red(e) for e in (f.get("entities") or [])],
            "measured_values": list(f.get("measured_values") or []),
            "comparison_basis": str(f.get("comparison_basis") or ""),
            "limitations": list(f.get("limitations") or []),
        })

    bms = []
    inv = investigation if isinstance(investigation, dict) else {}
    for b in inv.get("bookmarks", []) or []:
        if not isinstance(b, dict):
            continue
        bms.append({
            "id": str(b.get("id") or ""),
            "type": str(b.get("type") or "observation"),
            "title": str(b.get("title") or ""),
            "note": str(b.get("note") or ""),
            "refs": [dict(r) for r in (b.get("refs") or []) if isinstance(r, dict)],
        })

    stats = []
    for s in statistics or []:
        if not isinstance(s, dict):
            continue
        stats.append({
            "name": str(s.get("name") or ""),
            "value": s.get("value"),
            "unit": str(s.get("unit") or ""),
            "sample_count": s.get("sample_count"),
            "entity": red(s.get("entity") or ""),
        })

    evc = []
    for e in event_context or []:
        if not isinstance(e, dict):
            continue
        evc.append({
            "time": e.get("time"),
            "kind": str(e.get("kind") or ""),
            "detail": red(e.get("detail") or e.get("task") or ""),
            "core": str(e.get("core") or ""),
        })

    health_block = None
    if isinstance(health, dict):
        health_block = {
            "status": str(health.get("status") or ""),
            "issue_count": int(health.get("issue_count", health.get("issueCount", 0)) or 0),
            "limitations": list(
                health.get("metric_limitations") or health.get("metricLimitations") or []),
        }

    package: Dict[str, Any] = {
        "schema": EVIDENCE_PACKAGE_SCHEMA,
        "question": str(question or "").strip(),
        "scope": str(scope or "").strip(),
        "analysis_range": (
            {"start": int(analysis_range["start"]), "end": int(analysis_range["end"])}
            if isinstance(analysis_range, dict) and analysis_range.get("start") is not None
            else None
        ),
        "trace": {
            "name": "(redacted)" if redact_names else str(trace_name or ""),
            "summary": _compact_summary(trace_summary),
        },
        "trace_health": health_block,
        "entities": [red(e) for e in (entities or [])],
        "cores": [str(c) for c in (cores or [])],
        "statistics": stats,
        "event_context": evc,
        "findings": fnd,
        "bookmarks": bms,
        "conclusion_so_far": str(inv.get("conclusion") or ""),
        "unresolved_questions": [str(q) for q in (inv.get("unresolved_questions") or [])],
        "instructions": _INSTRUCTIONS,
        "response_contract": list(RESPONSE_CONTRACT),
        "redacted": bool(redact_names),
    }
    if redact_names and alias_map:
        package["alias_note"] = "Task names replaced with task_N aliases for privacy."
    return package


_SUMMARY_KEYS = (
    "span_ns", "tasks", "segments", "sti_events", "context_switches",
    "gap_avg_ns", "gap_max_ns", "migrations", "migrated_tasks",
    "load_balance_score", "load_balance_sigma", "tick_health", "missed_ticks",
    "time_scale",
)


def _compact_summary(summary: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    if not isinstance(summary, dict):
        return {}
    return {k: summary[k] for k in _SUMMARY_KEYS if k in summary and summary[k] is not None}


# --------------------------------------------------------------------------
def estimate_tokens(package: Dict[str, Any]) -> int:
    """Rough token estimate for the serialised package (~4 chars/token)."""
    text = json.dumps(package, ensure_ascii=False, sort_keys=True)
    return max(1, (len(text) + 3) // 4)


def evidence_package_size(package: Dict[str, Any]) -> Dict[str, int]:
    text = json.dumps(package, ensure_ascii=False, sort_keys=True)
    return {
        "bytes": len(text.encode("utf-8")),
        "chars": len(text),
        "approx_tokens": estimate_tokens(package),
        "findings": len(package.get("findings") or []),
        "bookmarks": len(package.get("bookmarks") or []),
        "statistics": len(package.get("statistics") or []),
        "event_context": len(package.get("event_context") or []),
    }


def format_evidence_package_preview(package: Dict[str, Any]) -> str:
    """Human-readable preview of exactly what would be sent."""
    lines: List[str] = []
    size = evidence_package_size(package)
    lines.append(f"Evidence package — ~{size['approx_tokens']} tokens, "
                 f"{size['bytes']:,} bytes"
                 + ("  (task names redacted)" if package.get("redacted") else ""))
    lines.append("")
    lines.append(f"Question: {package.get('question') or '(none)'}")
    if package.get("scope"):
        lines.append(f"Scope: {package['scope']}")
    rng = package.get("analysis_range")
    if rng:
        lines.append(f"Range: {rng['start']} – {rng['end']}")
    th = package.get("trace_health")
    if th:
        lim = f"; limited: {', '.join(th['limitations'])}" if th.get("limitations") else ""
        lines.append(f"Trace health: {th['status']} ({th['issue_count']} issue(s)){lim}")
    if package.get("entities"):
        lines.append(f"Entities: {', '.join(package['entities'][:20])}")
    if package.get("statistics"):
        lines.append(f"Statistics ({len(package['statistics'])}):")
        for s in package["statistics"][:20]:
            sc = f", n={s['sample_count']}" if s.get("sample_count") is not None else ""
            ent = f" [{s['entity']}]" if s.get("entity") else ""
            lines.append(f"  - {s['name']}{ent} = {s['value']} {s['unit']}{sc}".rstrip())
    if package.get("findings"):
        lines.append(f"Findings ({len(package['findings'])}):")
        for f in package["findings"]:
            lines.append(f"  [{f['id']}] {f['severity']}: {f['observation']}")
    if package.get("bookmarks"):
        lines.append(f"Bookmarks ({len(package['bookmarks'])}):")
        for b in package["bookmarks"]:
            lines.append(f"  ({b['type']}) {b['title']}")
    if package.get("event_context"):
        lines.append(f"Event context: {len(package['event_context'])} event(s) "
                     "around the range")
    if package.get("conclusion_so_far"):
        lines.append(f"Conclusion so far: {package['conclusion_so_far']}")
    lines.append("")
    lines.append("Response contract: " + " · ".join(package.get("response_contract", [])))
    lines.append(package.get("instructions", ""))
    return "\n".join(lines) + "\n"
