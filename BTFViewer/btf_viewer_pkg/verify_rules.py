"""Headless verification against a JSON rule file.

``btfviewer verify trace.btf --rules rules.json`` resolves each rule's metric
for the trace (optionally a cursor scope), compares it to the configured
threshold, and returns a stable exit code:

* ``0`` — every rule passed (warnings alone still pass unless ``--strict``)
* ``1`` — one or more ``error``-severity limits failed
* ``2`` — invalid input: bad rule file, unknown metric, or insufficient data
* ``3`` — internal processing error (raised by the caller)

Rule file (JSON)::

    {
      "schema_version": 1,
      "rules": [
        {"metric": "load_balance_score", "min": 70, "severity": "error"},
        {"metric": "migrations", "max": 500, "severity": "warning"},
        {"metric": "gap_max_us", "max": 50},
        {"metric": "trace_health", "expect_one_of": ["pass", "caution"]}
      ]
    }

Thresholds: ``min`` / ``max`` (native units), ``minimum_us`` / ``maximum_us``
(and ``_ms`` / ``_ns``) for time metrics, ``expect`` / ``expect_one_of`` for
status metrics. A metric name may itself carry a ``_us`` / ``_ms`` suffix
(``gap_max_us``) as a display-unit convenience.

Only trace-wide and structural-health metrics are supported in this version;
a rule scoped to an ``entity`` on an unsupported metric fails with exit code 2.
"""
from __future__ import annotations

import json
from typing import Any, Dict, List, Optional, Tuple

VERIFY_SCHEMA_VERSION = 1

EXIT_PASS = 0
EXIT_FAIL = 1
EXIT_INPUT = 2
EXIT_INTERNAL = 3

_SEVERITIES = ("info", "warning", "error")

# metric -> (snapshot key, kind).  kind: "number" | "time_ns" | "status"
_TRACE_METRICS: Dict[str, Tuple[str, str]] = {
    "span_ns": ("span_ns", "time_ns"),
    "tasks": ("tasks", "number"),
    "segments": ("segments", "number"),
    "sti_events": ("sti_events", "number"),
    "context_switches": ("context_switches", "number"),
    "gap_avg_ns": ("gap_avg_ns", "time_ns"),
    "gap_max_ns": ("gap_max_ns", "time_ns"),
    "migrations": ("migrations", "number"),
    "migrated_tasks": ("migrated_tasks", "number"),
    "load_balance_score": ("load_balance_score", "number"),
    "load_balance_sigma": ("load_balance_sigma", "number"),
    "tick_health": ("tick_health", "status"),
    "tick_count": ("tick_count", "number"),
    "missed_ticks": ("missed_ticks", "number"),
}

# Derived metrics resolved from build_trace_health_result / the snapshot.
_DERIVED_METRICS = {"trace_health", "migration_rate_per_s"}

_TIME_UNIT_DIVISOR = {"ns": 1.0, "us": 1_000.0, "ms": 1_000_000.0, "s": 1_000_000_000.0}
_HEALTH_RANK = {"pass": 0, "caution": 1, "insufficient": 2}


def supported_metrics() -> List[str]:
    """Sorted list of every metric name a rule may target."""
    return sorted(set(_TRACE_METRICS) | _DERIVED_METRICS)


# --------------------------------------------------------------------------
def load_rule_file(path: str) -> Dict[str, Any]:
    """Parse + validate a JSON rule file. Raises ``ValueError`` on any problem."""
    try:
        with open(path, "r", encoding="utf-8") as fh:
            raw = fh.read()
    except OSError as exc:  # pragma: no cover - surfaced by the caller
        raise ValueError(f"cannot read rule file: {exc}") from exc
    return parse_rules(raw)


def parse_rules(text: str) -> Dict[str, Any]:
    try:
        obj = json.loads(text)
    except (json.JSONDecodeError, ValueError) as exc:
        raise ValueError(f"rule file is not valid JSON: {exc}") from exc
    if not isinstance(obj, dict):
        raise ValueError("rule file must be a JSON object")
    ver = obj.get("schema_version", VERIFY_SCHEMA_VERSION)
    if ver != VERIFY_SCHEMA_VERSION:
        raise ValueError(
            f"unsupported rule schema_version {ver!r} (expected {VERIFY_SCHEMA_VERSION})")
    rules = obj.get("rules")
    if not isinstance(rules, list) or not rules:
        raise ValueError("rule file has no 'rules' array")
    norm = [normalize_rule(r, i) for i, r in enumerate(rules)]
    return {"schema_version": VERIFY_SCHEMA_VERSION, "rules": norm}


def normalize_rule(rule: Any, index: int = 0) -> Dict[str, Any]:
    if not isinstance(rule, dict):
        raise ValueError(f"rule #{index + 1} is not an object")
    metric = str(rule.get("metric") or "").strip()
    if not metric:
        raise ValueError(f"rule #{index + 1} has no 'metric'")
    out: Dict[str, Any] = {
        "metric": metric,
        "entity": str(rule.get("entity") or "").strip(),
        "severity": _clean_severity(rule.get("severity")),
        "label": str(rule.get("label") or "").strip(),
    }
    # Threshold: min/max (native) or minimum_<unit>/maximum_<unit>, or expect*.
    lo = _first_present(rule, ("min", "minimum"))
    hi = _first_present(rule, ("max", "maximum"))
    unit = "ns"
    for u in ("ns", "us", "ms", "s"):
        if f"minimum_{u}" in rule:
            lo, unit = rule[f"minimum_{u}"], u
        if f"maximum_{u}" in rule:
            hi, unit = rule[f"maximum_{u}"], u
    expect = rule.get("expect")
    expect_one_of = rule.get("expect_one_of")

    if expect is not None:
        out["expect"] = [str(expect)]
    elif isinstance(expect_one_of, list) and expect_one_of:
        out["expect"] = [str(x) for x in expect_one_of]
    elif lo is None and hi is None:
        raise ValueError(
            f"rule #{index + 1} ({metric}) has no threshold "
            "(min / max / minimum_us / maximum_us / expect / expect_one_of)")
    if lo is not None:
        out["min"] = float(lo)
    if hi is not None:
        out["max"] = float(hi)
    if lo is not None or hi is not None:
        out["threshold_unit"] = unit
    return out


def _first_present(d: Dict[str, Any], keys: Tuple[str, ...]) -> Optional[Any]:
    for k in keys:
        if k in d:
            return d[k]
    return None


def _clean_severity(value: Any) -> str:
    s = str(value or "error").strip().lower()
    return s if s in _SEVERITIES else "error"


# --------------------------------------------------------------------------
def _split_unit_suffix(metric: str) -> Tuple[str, str]:
    """('gap_max_us', ...) -> ('gap_max', 'us'); 'gap_max_ns' stays ('gap_max_ns','ns')."""
    for u in ("us", "ms"):
        if metric.endswith("_" + u):
            return metric[: -(len(u) + 1)], u
    return metric, "ns"


def _canonical_metric(name: str) -> Optional[Tuple[str, Tuple[str, str], str]]:
    """Resolve a rule metric name to (canonical, (snapshot_key, kind), display_unit)."""
    if name in _TRACE_METRICS:
        return name, _TRACE_METRICS[name], "ns"
    base, unit = _split_unit_suffix(name)
    if base in _TRACE_METRICS:
        return base, _TRACE_METRICS[base], unit
    if base + "_ns" in _TRACE_METRICS:
        return base + "_ns", _TRACE_METRICS[base + "_ns"], unit
    return None


def resolve_metric(
    metric: str, snapshot: Dict[str, Any], health: Optional[Dict[str, Any]],
) -> Tuple[Optional[float], str, str]:
    """(value, kind, reason). ``value`` is None when the metric cannot be
    resolved; ``reason`` explains why. ``kind`` is 'number' | 'status'."""
    name = str(metric or "").strip()

    if name == "trace_health":
        status = str((health or {}).get("status") or "").strip().lower()
        if status not in _HEALTH_RANK:
            return None, "status", "trace health was not computed"
        return float(_HEALTH_RANK[status]), "status", ""

    if name == "migration_rate_per_s":
        span = float(snapshot.get("span_ns") or 0)
        migs = float(snapshot.get("migrations") or 0)
        if span <= 0:
            return None, "number", "trace span is zero"
        return migs / (span / 1e9), "number", ""

    canon = _canonical_metric(name)
    if canon is None:
        return None, "number", f"unknown metric '{name}'"
    _canonical, (key, kind), disp_unit = canon
    val = snapshot.get(key)
    if val is None:
        return None, kind, "insufficient data for this metric"
    if kind == "status":
        return None, "status", ""  # compared via expect only; see evaluate_rule
    fval = float(val)
    if kind == "time_ns" and disp_unit != "ns":
        fval = fval / _TIME_UNIT_DIVISOR.get(disp_unit, 1.0)
    return fval, "number", ""


def evaluate_rule(
    rule: Dict[str, Any], snapshot: Dict[str, Any], health: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
    metric = rule["metric"]
    out: Dict[str, Any] = {
        "metric": metric,
        "entity": rule.get("entity", ""),
        "severity": rule.get("severity", "error"),
        "label": rule.get("label") or metric,
        "status": "pass",
        "value": None,
        "message": "",
    }

    # Per-entity rules on trace-wide metrics are not supported yet.
    if rule.get("entity") and metric not in _DERIVED_METRICS \
            and _canonical_metric(metric) is None:
        out["status"] = "error"
        out["message"] = (
            f"per-entity metric '{metric}' for '{rule['entity']}' is not "
            "supported by verify yet")
        return out

    # Status metrics: string equality against expect list.
    is_status_metric = (
        metric == "tick_health"
        or (_TRACE_METRICS.get(metric, ("", ""))[1] == "status"))
    if is_status_metric:
        actual = str(snapshot.get(_TRACE_METRICS[metric][0]) or "").strip()
        out["value"] = actual
        want = [str(x) for x in rule.get("expect", [])]
        if not want:
            out["status"] = "error"
            out["message"] = f"metric '{metric}' needs expect / expect_one_of"
        elif not actual:
            out["status"] = "error"
            out["message"] = "insufficient data for this metric"
        elif actual not in want:
            out["status"] = "fail"
            out["message"] = f"{actual!r} not in {want}"
        return out

    if metric == "trace_health":
        status = str((health or {}).get("status") or "").strip().lower()
        out["value"] = status or None
        if "expect" in rule:
            want = [str(x).lower() for x in rule["expect"]]
            if status not in _HEALTH_RANK:
                out["status"] = "error"
                out["message"] = "trace health was not computed"
            elif status not in want:
                out["status"] = "fail"
                out["message"] = f"structural health {status!r} not in {want}"
            return out
        # numeric worst-allowed via max (0=pass,1=caution,2=insufficient)
        rank = _HEALTH_RANK.get(status)
        if rank is None:
            out["status"] = "error"
            out["message"] = "trace health was not computed"
            return out
        limit = int(rule.get("max", 1))
        if rank > limit:
            out["status"] = "fail"
            out["message"] = (
                f"structural health {status!r} worse than the allowed rank {limit}")
        return out

    value, _kind, reason = resolve_metric(metric, snapshot, health)
    out["value"] = value
    if value is None:
        out["status"] = "error"
        out["message"] = reason or "metric could not be resolved"
        return out
    lo = rule.get("min")
    hi = rule.get("max")
    if lo is not None and value < lo:
        out["status"] = "fail"
        out["message"] = f"{_vr_num(value)} < min {_vr_num(lo)}"
    elif hi is not None and value > hi:
        out["status"] = "fail"
        out["message"] = f"{_vr_num(value)} > max {_vr_num(hi)}"
    return out


def _vr_num(v: float) -> str:
    if v == int(v):
        return str(int(v))
    return f"{v:.3f}".rstrip("0").rstrip(".")


# --------------------------------------------------------------------------
def run_verification(
    snapshot: Dict[str, Any],
    health: Optional[Dict[str, Any]],
    rules: Dict[str, Any],
    *,
    strict: bool = False,
) -> Dict[str, Any]:
    results = [evaluate_rule(r, snapshot, health) for r in rules.get("rules", [])]
    failed = [r for r in results if r["status"] == "fail"]
    errored = [r for r in results if r["status"] == "error"]
    passed = [r for r in results if r["status"] == "pass"]

    exit_code = EXIT_PASS
    if errored:
        exit_code = EXIT_INPUT
    blocking = [
        r for r in failed
        if r["severity"] == "error" or (strict and r["severity"] == "warning")
    ]
    if blocking and exit_code == EXIT_PASS:
        exit_code = EXIT_FAIL
    elif blocking:  # keep the more severe of FAIL / INPUT? failing limits win.
        exit_code = EXIT_FAIL if not errored else EXIT_INPUT

    return {
        "results": results,
        "passed": len(passed),
        "failed": len(failed),
        "errored": len(errored),
        "blocking": len(blocking),
        "exit_code": exit_code,
        "strict": bool(strict),
    }


def format_verification_report(result: Dict[str, Any], *, title: str = "") -> str:
    lines: List[str] = []
    if title:
        lines.append(f"Verify: {title}")
    tag = {"pass": "PASS", "fail": "FAIL", "error": "DATA"}
    for r in result.get("results", []):
        val = r.get("value")
        val_s = "—" if val is None else (val if isinstance(val, str) else _vr_num(float(val)))
        ent = f" [{r['entity']}]" if r.get("entity") else ""
        msg = f"  {r['message']}" if r.get("message") else ""
        lines.append(
            f"  {tag.get(r['status'], '?'):4}  {r['label']}{ent} = {val_s}"
            f"  ({r['severity']}){msg}")
    lines.append(
        f"  {result['passed']} passed, {result['failed']} failed, "
        f"{result['errored']} data error(s) → exit {result['exit_code']}")
    return "\n".join(lines) + "\n"
