"""Investigation Findings — structured model, rule catalog, dedup, ranking.

Lockstep with ``web/src/utils/investigationFindings.js``.

This is an additive layer over the loose finding dicts produced by
``stats._build_workflow_analysis_findings`` (and its web twin
``workflowAnalysis.buildWorkflowAnalysisFindings``). It does not replace the
rule producers; it:

* normalises any finding dict into the canonical ``InvestigationFinding`` shape
  (measured values and thresholds kept separate from display text so exports
  stay reproducible and localizable),
* enumerates every deterministic rule the engine can emit (``RULE_CATALOG``) —
  the stable "rule interface",
* deduplicates findings that describe the same rule + entity + overlapping
  range,
* ranks findings by severity, magnitude, duration, and evidence quality.

Everything here is a pure function of its inputs.
"""
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Sequence

from .findings_triage import (
    QUEUE_CASE,
    QUEUE_DISMISSED,
    QUEUE_DONE,
    finding_category,
    finding_evidence_strength,
    finding_queue_status,
)

# Empty-state wording — the spec is explicit: "No findings under the current
# rules", never "No problems".
NO_FINDINGS_UNDER_RULES = "No findings under the current rules"

FINDING_STATUS_NEW = "new"
FINDING_STATUS_REVIEWED = "reviewed"
FINDING_STATUS_BOOKMARKED = "bookmarked"
FINDING_STATUS_DISMISSED = "dismissed"
FINDING_STATUSES = (
    FINDING_STATUS_NEW,
    FINDING_STATUS_REVIEWED,
    FINDING_STATUS_BOOKMARKED,
    FINDING_STATUS_DISMISSED,
)

_QUEUE_TO_STATUS = {
    QUEUE_DONE: FINDING_STATUS_REVIEWED,
    QUEUE_CASE: FINDING_STATUS_BOOKMARKED,
    QUEUE_DISMISSED: FINDING_STATUS_DISMISSED,
}

_SEVERITY_WEIGHT = {"error": 1.0, "warning": 0.66, "info": 0.33, "ask": 0.15}
_EVIDENCE_QUALITY = {"direct": 1.0, "derived": 0.6, "estimated": 0.3, "configured": 0.6}
_MAGNITUDE_BY_SEVERITY = {"error": 0.85, "warning": 0.55, "info": 0.25, "ask": 0.15}

# Ranking blend. Severity dominates; the rest break ties and float bounded
# observations up. Weights sum to 1.
_W_SEVERITY = 0.50
_W_MAGNITUDE = 0.25
_W_DURATION = 0.15
_W_EVIDENCE = 0.10

# A range covering this fraction of the analysed span earns full duration weight.
_DURATION_FULL_FRACTION = 0.25

_CORE_RE = re.compile(r"\bCore[_ ]?\d+\b", re.I)
_UNIT = r"(?P<unit>%|ns|µs|us|μs|ms|s)?"
# Two conservative forms only:
#   1. explicit "key=value" / "key: value"  (key is a short token, no spaces/parens)
#   2. a whitelisted label followed by a number ("Max 10us", "CV 4.2%", "n 42")
_MEASURE_RE = re.compile(
    r"(?:(?P<n1>[A-Za-zµσ][\w./%-]{0,23})\s*[=:]\s*(?P<v1>-?\d+(?:\.\d+)?)\s*" + _UNIT + r")"
    r"|(?:\b(?P<n2>Max|Min|Avg|Mean|Median|CV|G|σ|n|p50|p95|p99|Count|Migr|"
    r"Rate|Score|Dwell|Ping|missed|Gap)\s+(?P<v2>-?\d+(?:\.\d+)?)\s*" + _UNIT.replace("unit", "unit2") + r")"
)
_UNIT_CANON = {"us": "µs", "μs": "µs", "µs": "µs"}


class RuleSpec:  # lightweight; a plain dict would do but this documents the shape
    __slots__ = ("rule_id", "severity", "category", "observation_kind",
                 "comparison_basis", "metric")

    def __init__(self, rule_id, severity, category, observation_kind,
                 comparison_basis, metric):
        self.rule_id = rule_id
        self.severity = severity
        self.category = category
        self.observation_kind = observation_kind
        self.comparison_basis = comparison_basis
        self.metric = metric

    def as_dict(self) -> Dict[str, str]:
        return {
            "rule_id": self.rule_id,
            "severity": self.severity,
            "category": self.category,
            "observation_kind": self.observation_kind,
            "comparison_basis": self.comparison_basis,
            "metric": self.metric,
        }


def _spec(*args) -> RuleSpec:
    return RuleSpec(*args)


# The deterministic rule interface: every rule_id the Analysis Findings engine
# can emit, with a stable comparison basis and target metric. Producers attach
# ``rule_id`` to their findings; consumers look the rest up here.
RULE_CATALOG: Dict[str, RuleSpec] = {
    r.rule_id: r for r in (
        _spec("load_imbalance", "warning", "load", "load_spike",
              "Gini of per-core utilisation vs even distribution",
              "Core Utilisation (excl. IDLE/TICK)"),
        _spec("load_balance_ok", "info", "load", "load_spike",
              "Gini of per-core utilisation vs even distribution",
              "Core Utilisation (excl. IDLE/TICK)"),
        _spec("load_balance_moderate", "info", "load", "load_spike",
              "Gini of per-core utilisation vs even distribution",
              "Core Utilisation (excl. IDLE/TICK)"),
        _spec("top_cpu", "info", "execution", "execution_time_high",
              "share of active CPU time in scope",
              "Top Tasks by CPU (excl. IDLE/TICK)"),
        _spec("exec_max", "info", "execution", "execution_time_high",
              "observed slice maxima (not proven WCET)",
              "Execution Time Per Slice"),
        _spec("wcet_anomaly", "warning", "execution", "execution_time_high",
              "slice Max vs the entity's own average",
              "Execution Time Per Slice"),
        _spec("exec_p95_exceeded", "warning", "execution", "execution_time_high",
              "slice duration vs the entity's p95",
              "Execution Time Per Slice"),
        _spec("blocking", "info", "blocking", "latency_outlier",
              "off-CPU gap count and Max vs peers",
              "Off-CPU Time (Blocking Time)"),
        _spec("wakeup_latency_outlier", "warning", "dispatch", "latency_outlier",
              "ready-to-run delay vs the entity's p95",
              "Dispatch / Scheduling Latency"),
        _spec("priority_inversion", "warning", "blocking", "latency_outlier",
              "L/M/H priority pattern around a held mutex",
              "Priority Inheritance"),
        _spec("thrashing", "warning", "migration", "migration_frequent",
              "migration rate / dwell / ping-pong vs heuristic thresholds",
              "Core Migrations"),
        _spec("hot_pairs", "warning", "migration", "migration_frequent",
              "directed core-pair traffic and lock-bounce share",
              "Core-Pair Migration Summary"),
        _spec("migration_burst_anomaly", "warning", "migration", "load_spike",
              "migration rate in a window vs the trace mean",
              "Core Migrations"),
        _spec("period_instability", "warning", "jitter", "period_instability",
              "inter-arrival CV and missed/extra activations vs nominal period",
              "Period / Jitter"),
        _spec("deadlines", "error", "deadline", "execution_time_high",
              "measured slice / CPU budget vs the configured limit",
              "Deadlines / CPU budget"),
        _spec("tick_health", "warning", "health", "period_instability",
              "TICK interval CV and large gaps vs the nominal period",
              "Trace Health (TICK)"),
        _spec("missed_ticks", "warning", "health", "long_gap",
              "large TICK gaps vs the nominal period",
              "Trace Health (TICK)"),
        _spec("long_gap", "info", "general", "long_gap",
              "longest unscheduled interval vs the analysed span",
              "Scheduling Load Over Time"),
        _spec("sync_bounce", "warning", "sync", "migration_frequent",
              "sync-object core bounces vs zero",
              "Mutex / Semaphore"),
        _spec("sync_issues", "warning", "sync", "missing_evidence",
              "unpaired take/give STI events vs zero",
              "Mutex / Semaphore"),
        _spec("baseline_regression", "warning", "general", "regression",
              "current metric vs the saved baseline value",
              "Trace Compare"),
        _spec("missing_evidence", "info", "general", "missing_evidence",
              "event types required by the metric vs what the trace contains",
              "Trace Health Check"),
        _spec("none", "info", "general", "missing_evidence",
              "no rule produced a finding in scope", "Analysis Findings"),
    )
}

RULE_IDS = tuple(RULE_CATALOG.keys())


def rule_spec(rule_id: str) -> Optional[RuleSpec]:
    return RULE_CATALOG.get(str(rule_id or "").strip())


# ---------------------------------------------------------------------------
# Measured-value extraction
# ---------------------------------------------------------------------------
def _canon_unit(u: Optional[str]) -> str:
    if not u:
        return ""
    return _UNIT_CANON.get(u, u)


def parse_measured_values(text: str) -> List[Dict[str, Any]]:
    """Best-effort ``{name, value, unit}`` list from an evidence string.

    Deterministic: same string always yields the same list. Used only as a
    fallback when a rule did not attach structured ``measured_values``.
    """
    out: List[Dict[str, Any]] = []
    seen: set = set()
    for m in _MEASURE_RE.finditer(str(text or "")):
        name = (m.group("n1") or m.group("n2") or "").strip(" .:=-") or "value"
        raw = m.group("v1") or m.group("v2")
        unit = _canon_unit(m.group("unit") or m.group("unit2"))
        try:
            value: Any = float(raw)
        except (TypeError, ValueError):
            continue
        if value.is_integer():
            value = int(value)
        key = (name.lower(), value, unit)
        if key in seen:
            continue
        seen.add(key)
        out.append({"name": name, "value": value, "unit": unit})
        if len(out) >= 8:
            break
    return out


def _normalize_measured_values(raw: Any, fallback_text: str) -> List[Dict[str, Any]]:
    items: List[Dict[str, Any]] = []
    if isinstance(raw, Sequence) and not isinstance(raw, (str, bytes)):
        for mv in raw:
            if not isinstance(mv, dict):
                continue
            if "name" not in mv or "value" not in mv:
                continue
            item = {
                "name": str(mv["name"]),
                "value": mv["value"],
                "unit": _canon_unit(str(mv.get("unit") or "")) or "",
            }
            if mv.get("sample_count") is not None:
                try:
                    item["sample_count"] = int(mv["sample_count"])
                except (TypeError, ValueError):
                    pass
            if mv.get("threshold") is not None:
                item["threshold"] = mv["threshold"]
            items.append(item)
    if items:
        return items
    return parse_measured_values(fallback_text)


# ---------------------------------------------------------------------------
# Entities / range / evidence
# ---------------------------------------------------------------------------
def _entities(raw: Dict[str, Any]) -> List[str]:
    ents = raw.get("entities")
    out: List[str] = []
    if isinstance(ents, Sequence) and not isinstance(ents, (str, bytes)):
        out = [str(e).strip() for e in ents if str(e).strip()]
    if not out:
        task = str(raw.get("task") or "").strip()
        if task:
            out.append(task)
    if not out:
        blob = f"{raw.get('title') or ''} {raw.get('text') or ''} {raw.get('evidence_text') or ''}"
        for m in _CORE_RE.finditer(blob):
            tok = m.group(0).replace(" ", "_")
            if tok not in out:
                out.append(tok)
    # Preserve first-seen order, drop dups.
    seen: set = set()
    uniq: List[str] = []
    for e in out:
        if e not in seen:
            seen.add(e)
            uniq.append(e)
    return uniq


def _evidence_refs(raw: Dict[str, Any]) -> List[Dict[str, Any]]:
    refs: List[Dict[str, Any]] = []
    for ev in raw.get("evidence") or []:
        if isinstance(ev, dict):
            label = str(ev.get("label") or ev.get("text") or "evidence")
            t = ev.get("time")
            if t is None:
                for k in ("start", "ns", "stop"):
                    if ev.get(k) is not None:
                        t = ev.get(k)
                        break
            ref: Dict[str, Any] = {"label": label}
            if t is not None:
                try:
                    ref["time"] = int(float(t))
                except (TypeError, ValueError):
                    pass
            refs.append(ref)
        elif ev:
            refs.append({"label": str(ev)})
    return refs


def _affected_range(raw: Dict[str, Any], refs: List[Dict[str, Any]]) -> Optional[Dict[str, int]]:
    rng = raw.get("affected_range")
    if isinstance(rng, dict) and rng.get("start") is not None and rng.get("end") is not None:
        try:
            return {"start": int(rng["start"]), "end": int(rng["end"])}
        except (TypeError, ValueError):
            pass
    times = sorted(r["time"] for r in refs if "time" in r)
    if not times:
        return None
    return {"start": int(times[0]), "end": int(times[-1])}


def _limitations(raw: Dict[str, Any]) -> List[str]:
    lims = raw.get("limitations")
    if isinstance(lims, Sequence) and not isinstance(lims, (str, bytes)):
        out = [str(x).strip() for x in lims if str(x).strip()]
        if out:
            return out
    conf = str(raw.get("confidence") or "").strip()
    low = conf.lower()
    if low.startswith(("low", "medium")) or "heuristic" in low or "estimate" in low:
        return [f"Confidence: {conf}"] if conf else ["Heuristic — verify on the timeline."]
    return []


def _status(raw: Dict[str, Any], fid: str, triage_state: Optional[Dict[str, Any]]) -> str:
    if triage_state is not None and fid:
        q = finding_queue_status(fid, triage_state)
        return _QUEUE_TO_STATUS.get(q, FINDING_STATUS_NEW)
    st = str(raw.get("status") or "").strip().lower()
    return st if st in FINDING_STATUSES else FINDING_STATUS_NEW


# ---------------------------------------------------------------------------
# Normalisation
# ---------------------------------------------------------------------------
def normalize_investigation_finding(
    raw: Dict[str, Any],
    *,
    triage_state: Optional[Dict[str, Any]] = None,
    total_span_ns: Optional[int] = None,
) -> Dict[str, Any]:
    """Upgrade a loose finding dict to the canonical ``InvestigationFinding``.

    Original keys are preserved (spread first) so existing consumers keep
    working; the canonical keys are then set/overwritten.
    """
    raw = dict(raw or {})
    fid = str(raw.get("id") or "").strip()
    rule_id = str(raw.get("rule_id") or raw.get("fid") or fid or "").strip()
    if rule_id and rule_id not in RULE_CATALOG:
        # Ids are slugged per-report ("thrashing-2"); fold the numeric suffix.
        base = re.sub(r"-\d+$", "", rule_id)
        if base in RULE_CATALOG:
            rule_id = base
    spec = RULE_CATALOG.get(rule_id)

    severity = str(raw.get("severity") or (spec.severity if spec else "info")).lower()
    observation = str(
        raw.get("observation") or raw.get("text") or raw.get("title") or ""
    ).strip()
    fallback_text = f"{raw.get('evidence_text') or ''} {raw.get('text') or ''}"
    refs = _evidence_refs(raw)
    rng = _affected_range(raw, refs)
    ev_strength = str(
        raw.get("evidence_strength") or finding_evidence_strength(raw)
    ).lower()

    out = {
        **raw,
        "id": fid or rule_id,
        "rule_id": rule_id or "general",
        "severity": severity,
        "observation": observation,
        "affected_range": rng,
        "entities": _entities(raw),
        "measured_values": _normalize_measured_values(
            raw.get("measured_values"), fallback_text),
        "comparison_basis": str(
            raw.get("comparison_basis")
            or (spec.comparison_basis if spec else "")
        ),
        "evidence_refs": refs,
        "limitations": _limitations(raw),
        "status": _status(raw, fid, triage_state),
        "category": str(raw.get("category") or (spec.category if spec else finding_category(raw))),
        "observation_kind": str(
            raw.get("observation_kind") or (spec.observation_kind if spec else "general")
        ),
        "evidence_strength": ev_strength,
    }
    out["rank_score"] = _rank_score(out, total_span_ns)
    return out


# ---------------------------------------------------------------------------
# Ranking
# ---------------------------------------------------------------------------
def _magnitude(finding: Dict[str, Any]) -> float:
    base = _MAGNITUDE_BY_SEVERITY.get(str(finding.get("severity") or "info"), 0.25)
    for mv in finding.get("measured_values") or []:
        name = str(mv.get("name") or "").lower()
        if name in ("ratio", "excess", "ratio_over_avg", "over"):
            try:
                return max(0.0, min(1.0, float(mv["value"]) / 10.0))
            except (TypeError, ValueError, KeyError):
                pass
        if mv.get("threshold") not in (None, 0):
            try:
                r = abs(float(mv["value"]) / float(mv["threshold"]))
                # A structured threshold refines magnitude but never sinks a
                # finding far below its same-severity peers.
                return max(0.5 * base, min(1.0, (r - 1.0)))
            except (TypeError, ValueError, ZeroDivisionError):
                pass
    n_ev = len(finding.get("evidence_refs") or [])
    return min(1.0, base + min(0.10, 0.02 * n_ev))


def _duration_norm(finding: Dict[str, Any], total_span_ns: Optional[int]) -> float:
    rng = finding.get("affected_range")
    if not (isinstance(rng, dict) and total_span_ns and total_span_ns > 0):
        return 0.0
    try:
        span = max(0, int(rng["end"]) - int(rng["start"]))
    except (TypeError, ValueError, KeyError):
        return 0.0
    frac = span / float(total_span_ns)
    return max(0.0, min(1.0, frac / _DURATION_FULL_FRACTION))


def _rank_score(finding: Dict[str, Any], total_span_ns: Optional[int]) -> float:
    sev = _SEVERITY_WEIGHT.get(str(finding.get("severity") or "info"), 0.33)
    mag = _magnitude(finding)
    dur = _duration_norm(finding, total_span_ns)
    evq = _EVIDENCE_QUALITY.get(str(finding.get("evidence_strength") or "estimated"), 0.3)
    score = (_W_SEVERITY * sev + _W_MAGNITUDE * mag
             + _W_DURATION * dur + _W_EVIDENCE * evq)
    return round(score, 6)


def rank_investigation_findings(
    findings: Sequence[Dict[str, Any]],
    *,
    total_span_ns: Optional[int] = None,
) -> List[Dict[str, Any]]:
    """Sort by composite rank (desc), then id (asc) for a stable order."""
    items = []
    for f in findings or []:
        if not isinstance(f, dict):
            continue
        g = dict(f)
        g["rank_score"] = _rank_score(g, total_span_ns)
        items.append(g)
    items.sort(key=lambda f: (-float(f.get("rank_score") or 0.0), str(f.get("id") or "")))
    return items


# ---------------------------------------------------------------------------
# Deduplication
# ---------------------------------------------------------------------------
_SEV_RANK = {"error": 3, "warning": 2, "info": 1, "ask": 0}


def _ranges_overlap(a: Optional[Dict[str, int]], b: Optional[Dict[str, int]]) -> bool:
    if a is None or b is None:
        return True  # a rule+entity match with no range on either side = same signal
    return int(a["start"]) <= int(b["end"]) and int(b["start"]) <= int(a["end"])


def _entities_intersect(a: Sequence[str], b: Sequence[str]) -> bool:
    if not a or not b:
        return not a and not b
    return bool(set(a) & set(b))


def _merge_pair(keep: Dict[str, Any], drop: Dict[str, Any]) -> Dict[str, Any]:
    out = dict(keep)
    out["entities"] = sorted(set(keep.get("entities") or []) | set(drop.get("entities") or []))
    a, b = keep.get("affected_range"), drop.get("affected_range")
    if a and b:
        out["affected_range"] = {
            "start": min(int(a["start"]), int(b["start"])),
            "end": max(int(a["end"]), int(b["end"])),
        }
    elif b and not a:
        out["affected_range"] = b
    seen = {(r.get("label"), r.get("time")) for r in keep.get("evidence_refs") or []}
    merged_refs = list(keep.get("evidence_refs") or [])
    for r in drop.get("evidence_refs") or []:
        k = (r.get("label"), r.get("time"))
        if k not in seen:
            seen.add(k)
            merged_refs.append(r)
    out["evidence_refs"] = merged_refs
    out["merged_count"] = int(keep.get("merged_count") or 1) + int(drop.get("merged_count") or 1)
    return out


def _prefer(a: Dict[str, Any], b: Dict[str, Any]) -> tuple:
    """Sort key: the finding that should survive a merge sorts first."""
    return (
        -_SEV_RANK.get(str(a.get("severity") or "info"), 1),
        -float(a.get("rank_score") or 0.0),
        -len(a.get("evidence_refs") or []),
        str(a.get("id") or ""),
    )


def dedupe_investigation_findings(
    findings: Sequence[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """Collapse findings with the same ``rule_id`` + intersecting entities +
    overlapping ``affected_range`` into one, keeping the strongest.

    Deterministic: input is stably pre-sorted, survivors keep input order.
    """
    items = [dict(f) for f in (findings or []) if isinstance(f, dict)]
    # Stable base order so the survivor pick and output order are reproducible.
    items.sort(key=lambda f: (str(f.get("rule_id") or ""), str(f.get("id") or "")))

    survivors: List[Dict[str, Any]] = []
    for f in items:
        rid = str(f.get("rule_id") or "")
        merged = False
        for i, s in enumerate(survivors):
            if str(s.get("rule_id") or "") != rid:
                continue
            if not _entities_intersect(f.get("entities") or [], s.get("entities") or []):
                continue
            if not _ranges_overlap(s.get("affected_range"), f.get("affected_range")):
                continue
            keep, drop = (s, f) if _prefer(s, f) <= _prefer(f, s) else (f, s)
            survivors[i] = _merge_pair(keep, drop)
            merged = True
            break
        if not merged:
            survivors.append(dict(f, merged_count=int(f.get("merged_count") or 1)))
    return survivors


# ---------------------------------------------------------------------------
# Pipeline
# ---------------------------------------------------------------------------
def build_investigation_findings(
    raw_findings: Sequence[Dict[str, Any]],
    *,
    triage_state: Optional[Dict[str, Any]] = None,
    total_span_ns: Optional[int] = None,
    dedupe: bool = True,
) -> List[Dict[str, Any]]:
    """normalise → (dedupe) → rank. Returns canonical InvestigationFindings."""
    norm = [
        normalize_investigation_finding(
            f, triage_state=triage_state, total_span_ns=total_span_ns)
        for f in (raw_findings or [])
        if isinstance(f, dict)
    ]
    if dedupe:
        norm = dedupe_investigation_findings(norm)
    return rank_investigation_findings(norm, total_span_ns=total_span_ns)


def investigation_finding_export(finding: Dict[str, Any]) -> Dict[str, Any]:
    """Trim a normalised finding to the fields worth serialising in reports."""
    return {
        "id": finding.get("id") or "",
        "rule_id": finding.get("rule_id") or "general",
        "severity": finding.get("severity") or "info",
        "status": finding.get("status") or FINDING_STATUS_NEW,
        "observation": finding.get("observation") or "",
        "category": finding.get("category") or "general",
        "comparison_basis": finding.get("comparison_basis") or "",
        "affected_range": finding.get("affected_range"),
        "entities": list(finding.get("entities") or []),
        "measured_values": list(finding.get("measured_values") or []),
        "evidence_refs": list(finding.get("evidence_refs") or []),
        "limitations": list(finding.get("limitations") or []),
        "rank_score": finding.get("rank_score"),
    }
