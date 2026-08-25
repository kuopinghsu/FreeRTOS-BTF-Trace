"""Causal / temporal investigation engines (Desktop). Keep in sync with web aiCausal.js.

Host-side heuristics over Analysis Findings — not an RTOS scheduler.
"""
from __future__ import annotations

import math
import re
from typing import Any, Dict, List, Optional, Sequence, Tuple

_TASK_RE = re.compile(r"([A-Za-z_][\w.-]*\s*\[[^\]]+\])")
_JUMP_RE = re.compile(r"jump:([0-9]+(?:\.[0-9]+)?)")
_NUM_RE = re.compile(r"([-+]?[0-9]*\.?[0-9]+)\s*(ms|us|µs|ns|%)?", re.I)

_EDGE_KINDS: Tuple[Tuple[str, Tuple[str, ...]], ...] = (
    ("blocks", ("block", "wait", "held by")),
    ("preempts", ("preempt",)),
    ("migrates-to", ("migrat", "affinity")),
    ("owns", ("mutex", "lock", "owns")),
    ("wakes", ("wake", "notify", "give")),
    ("inherits-priority-from", ("inherit", "inversion")),
    ("depends-on", ("depend", "after", "caused")),
)

_BUCKETS: Tuple[Tuple[str, Tuple[str, ...]], ...] = (
    ("mutex_blocking", ("mutex", "lock", "contention", "block", "wait")),
    ("preemption", ("preempt", "isr", "interrupt")),
    ("migration", ("migrat", "affinity", "bounce")),
    ("execution", ("wcet", "execution", "runtime", "cpu")),
    ("scheduler", ("tick", "ready", "queue")),
)

_MEMORY: List[Dict[str, Any]] = []


def investigation_memory_store() -> List[Dict[str, Any]]:
    return list(_MEMORY)


def set_investigation_memory(rows: Optional[Sequence[dict]] = None) -> None:
    _MEMORY.clear()
    for row in rows or []:
        if isinstance(row, dict):
            _MEMORY.append(dict(row))


def _items(findings: Optional[Sequence[dict]]) -> List[dict]:
    return [f for f in (findings or []) if isinstance(f, dict)]


def _blob(finding: dict) -> str:
    return f"{finding.get('title') or ''} {finding.get('text') or ''}"


def _task_of(finding: dict) -> str:
    t = str(finding.get("task") or "").strip()
    if t:
        return t
    m = _TASK_RE.search(_blob(finding))
    return m.group(1).replace(" ", "") if m else ""


def _time_of(finding: dict) -> Optional[float]:
    for key in ("time", "ns", "t", "start", "when"):
        try:
            return float(finding[key])
        except (KeyError, TypeError, ValueError):
            continue
    m = _JUMP_RE.search(_blob(finding))
    if m:
        try:
            return float(m.group(1))
        except ValueError:
            return None
    return None


def _jumps(text: str) -> List[float]:
    out: List[float] = []
    for m in _JUMP_RE.finditer(str(text or "")):
        try:
            out.append(float(m.group(1)))
        except ValueError:
            continue
    return out


def _kind_of(text: str) -> str:
    blob = str(text or "").lower()
    for name, keys in _EDGE_KINDS:
        if any(k in blob for k in keys):
            return name
    return "correlates-with"


def _bucket_of(text: str) -> str:
    blob = str(text or "").lower()
    for name, keys in _BUCKETS:
        if any(k in blob for k in keys):
            return name
    return "other"


def _magnitude(finding: dict) -> float:
    for key in ("delta_ms", "ms", "duration", "value", "pct"):
        try:
            return abs(float(finding[key]))
        except (KeyError, TypeError, ValueError):
            continue
    m = _NUM_RE.search(_blob(finding))
    if not m:
        return 1.0
    try:
        n = abs(float(m.group(1)))
    except ValueError:
        return 1.0
    unit = (m.group(2) or "").lower()
    if unit == "ms":
        return n
    if unit in ("us", "µs"):
        return n / 1000.0
    if unit == "ns":
        return n / 1e6
    return n


def analyze_temporal_causality(
    findings: Optional[Sequence[dict]] = None,
    *,
    task: str = "",
) -> Dict[str, Any]:
    """Order findings in time and emit a happens-before chain (heuristic)."""
    items = _items(findings)
    want = str(task or "").strip()
    rows: List[dict] = []
    for f in items:
        t = _time_of(f)
        name = _task_of(f)
        if want and name and want not in name and name not in want:
            if want.lower() not in _blob(f).lower():
                continue
        rows.append({
            "time": t,
            "task": name,
            "title": str(f.get("title") or f.get("id") or ""),
            "kind": _kind_of(_blob(f)),
            "jump": f"jump:{int(t)}" if t is not None else "",
        })
    rows.sort(key=lambda r: (r["time"] is None, r["time"] if r["time"] is not None else 0))
    chain: List[str] = []
    for i, row in enumerate(rows):
        label = row["title"] or row["task"] or f"event {i + 1}"
        when = row["jump"] or "untimed"
        chain.append(f"{when}  {row['kind']}  {label}")
    mermaid = "flowchart TB\n"
    for i, row in enumerate(rows[:12]):
        nid = f"E{i}"
        mermaid += f'  {nid}["{(row["title"] or row["task"] or nid)[:48]}"]\n'
        if i:
            mermaid += f"  E{i - 1} --> {nid}\n"
    if not rows:
        mermaid += '  empty["No timed findings"]\n'
    focus = want or (rows[0]["task"] if rows else "")
    return {
        "ok": True,
        "message": (
            f"Temporal chain for {focus or 'scope'}: {len(rows)} events"
            if rows else "No timed findings to order"
        ),
        "task": focus,
        "events": rows,
        "chain": chain,
        "mermaid": mermaid,
        "disclaimer": "Heuristic happens-before from Findings times, not a kernel trace replay.",
    }


_GRAPH_MAX_NODES = 24
_GRAPH_MAX_EDGES = 40
_CAUSAL_EDGE_KINDS = frozenset((
    "blocks", "preempts", "depends-on", "owns", "waits-for",
    "wakes", "signals", "inherits-priority-from",
))


def _node_type(name: str, hint: str = "") -> str:
    if hint:
        return hint
    low = str(name or "").lower()
    if low.startswith("core") or str(name or "").startswith("Core_"):
        return "core"
    if low.startswith("mutex"):
        return "mutex"
    if low.startswith("sem"):
        return "sem"
    if low.startswith("queue"):
        return "queue"
    if "isr" in low:
        return "isr"
    if "[" in str(name or ""):
        return "task"
    return "resource"


def _matches_focus(name: str, want: str) -> bool:
    if not want:
        return True
    a, b = str(name or ""), str(want or "")
    return bool(a) and (b in a or a in b or b.lower() in a.lower())


def _add_dep_edge(
    bag: Dict[Tuple[str, str, str], dict],
    src: str,
    dst: str,
    kind: str,
    *,
    weight: float = 1.0,
    src_type: str = "",
    dst_type: str = "",
) -> None:
    src, dst = str(src or "").strip(), str(dst or "").strip()
    if not src or not dst or src == dst:
        return
    try:
        w = abs(float(weight))
    except (TypeError, ValueError):
        w = 1.0
    if w <= 0:
        w = 1.0
    key = (src, dst, kind)
    rec = bag.get(key)
    if rec:
        rec["count"] += 1
        rec["weight"] += w
        return
    bag[key] = {
        "from": src,
        "to": dst,
        "kind": kind,
        "count": 1,
        "weight": w,
        "from_type": _node_type(src, src_type),
        "to_type": _node_type(dst, dst_type),
    }


def collect_dependency_edges(
    *,
    sync_holds: Optional[Sequence[dict]] = None,
    preemptions: Optional[Sequence[dict]] = None,
    migrations: Optional[Sequence[dict]] = None,
    priority_episodes: Optional[Sequence[dict]] = None,
) -> List[dict]:
    """Typed edges from compact BTF records (not finding text)."""
    bag: Dict[Tuple[str, str, str], dict] = {}
    by_key: Dict[str, List[dict]] = {}
    for raw in sync_holds or []:
        if not isinstance(raw, dict):
            continue
        kind = str(raw.get("kind") or "").lower()
        key = str(raw.get("key") or f"{kind}:{raw.get('ptr') or kind or 'sync'}")
        holder = str(raw.get("holder") or raw.get("holder_label") or "").strip()
        try:
            start = float(raw.get("start_ns") if raw.get("start_ns") is not None
                          else raw.get("startNs") or 0)
        except (TypeError, ValueError):
            start = 0.0
        try:
            dur = float(raw.get("duration_ns") if raw.get("duration_ns") is not None
                        else raw.get("durationNs") or 0)
        except (TypeError, ValueError):
            dur = 0.0
        rec = {
            "kind": kind,
            "key": key,
            "holder": holder,
            "start": start,
            "duration": dur if dur > 0 else 1.0,
            "signal": bool(raw.get("signal")),
        }
        by_key.setdefault(key, []).append(rec)
    for key, holds in by_key.items():
        holds.sort(key=lambda h: h["start"])
        kind = holds[0]["kind"] or "resource"
        for h in holds:
            if h["holder"]:
                _add_dep_edge(
                    bag, h["holder"], key, "owns",
                    weight=h["duration"], src_type="task", dst_type=kind)
                if h["signal"] or kind in ("sem", "queue"):
                    _add_dep_edge(
                        bag, h["holder"], key, "signals",
                        weight=h["duration"], src_type="task", dst_type=kind)
        for prev, cur in zip(holds, holds[1:]):
            a, b = prev["holder"], cur["holder"]
            if not a or not b or a == b:
                continue
            _add_dep_edge(
                bag, b, key, "waits-for",
                weight=cur["duration"], src_type="task", dst_type=kind)
            _add_dep_edge(
                bag, a, b, "blocks",
                weight=prev["duration"], src_type="task", dst_type="task")
            _add_dep_edge(
                bag, b, a, "depends-on",
                weight=prev["duration"], src_type="task", dst_type="task")
            if prev["signal"] or kind in ("sem", "queue"):
                _add_dep_edge(
                    bag, a, b, "wakes",
                    weight=prev["duration"], src_type="task", dst_type="task")
    for raw in preemptions or []:
        if not isinstance(raw, dict):
            continue
        pre = str(raw.get("preemptor") or "").strip()
        vic = str(raw.get("victim") or "").strip()
        try:
            w = float(raw.get("weight") if raw.get("weight") is not None
                      else raw.get("count") or 1)
        except (TypeError, ValueError):
            w = 1.0
        _add_dep_edge(bag, pre, vic, "preempts", weight=w,
                      src_type="task", dst_type="task")
    for raw in migrations or []:
        if not isinstance(raw, dict):
            continue
        task = str(raw.get("task") or "").strip()
        core = str(raw.get("to_core") or raw.get("toCore") or "").strip()
        _add_dep_edge(bag, task, core, "migrates-to", weight=1.0,
                      src_type="task", dst_type="core")
    for raw in priority_episodes or []:
        if not isinstance(raw, dict):
            continue
        inherited = bool(raw.get("inherited") or raw.get("inversion_suspect")
                         or raw.get("inversionSuspect"))
        if not inherited:
            continue
        task = str(raw.get("task") or raw.get("task_label") or "").strip()
        mediums = raw.get("medium_tasks") or raw.get("mediumTasks") or []
        donors = [str(m).strip() for m in mediums if str(m).strip()]
        if not donors:
            donors = ["priority"]
        for donor in donors[:4]:
            _add_dep_edge(
                bag, task, donor, "inherits-priority-from",
                weight=1.0, src_type="task",
                dst_type="task" if "[" in donor else "resource")
    return sorted(
        bag.values(),
        key=lambda e: (-float(e.get("weight") or 0), e["from"], e["to"], e["kind"]),
    )


def _filter_graph_neighborhood(
    edges: Sequence[dict],
    want: str,
    hops: int = 2,
) -> List[dict]:
    if not want:
        return list(edges)
    keep = {e["from"] for e in edges if _matches_focus(e["from"], want)}
    keep |= {e["to"] for e in edges if _matches_focus(e["to"], want)}
    if not keep:
        return list(edges)
    for _ in range(max(0, hops)):
        extra = set()
        for e in edges:
            if e["from"] in keep or e["to"] in keep:
                extra.add(e["from"])
                extra.add(e["to"])
        keep |= extra
    return [e for e in edges if e["from"] in keep and e["to"] in keep]


def _responsible_tasks(edges: Sequence[dict], want: str) -> List[str]:
    if not want:
        return []
    seeds = {e["to"] for e in edges if _matches_focus(e["to"], want)}
    seeds |= {e["from"] for e in edges if _matches_focus(e["from"], want)}
    if not seeds:
        return []
    rev: Dict[str, List[str]] = {}
    types: Dict[str, str] = {}
    for e in edges:
        types[e["from"]] = e.get("from_type") or _node_type(e["from"])
        types[e["to"]] = e.get("to_type") or _node_type(e["to"])
        if e.get("kind") not in _CAUSAL_EDGE_KINDS:
            continue
        rev.setdefault(e["to"], []).append(e["from"])
    seen = set(seeds)
    stack = list(seeds)
    while stack:
        cur = stack.pop()
        for src in rev.get(cur, ()):
            if src in seen:
                continue
            seen.add(src)
            stack.append(src)
    out = []
    for name in seen:
        if name in seeds:
            continue
        if types.get(name) != "task" and "[" not in name:
            continue
        out.append(name)
    out.sort()
    return out[:12]


def _cap_graph_edges(
    edges: Sequence[dict],
    *,
    max_nodes: int = _GRAPH_MAX_NODES,
    max_edges: int = _GRAPH_MAX_EDGES,
) -> List[dict]:
    ranked = list(edges)
    picked: List[dict] = []
    nodes: set = set()
    for e in ranked:
        nxt = nodes | {e["from"], e["to"]}
        if len(picked) >= max_edges:
            break
        if len(nxt) > max_nodes and e["from"] not in nodes and e["to"] not in nodes:
            continue
        if len(nxt) > max_nodes and not (e["from"] in nodes or e["to"] in nodes):
            continue
        if len(nxt) > max_nodes:
            continue
        picked.append(e)
        nodes = nxt
    return picked


def _edges_from_findings(findings: Optional[Sequence[dict]]) -> List[dict]:
    bag: Dict[Tuple[str, str, str], dict] = {}
    for f in _items(findings):
        src = _task_of(f) or str(f.get("title") or f.get("id") or "finding")
        kind = _kind_of(_blob(f))
        others = [
            m.group(1).replace(" ", "")
            for m in _TASK_RE.finditer(_blob(f))
        ]
        dsts = [o for o in others if o != src][:3]
        if not dsts:
            blob = _blob(f)
            for token in ("Mutex", "Sem", "Queue", "ISR"):
                if token.lower() in blob.lower():
                    dsts = [token]
                    break
        for dst in dsts:
            _add_dep_edge(bag, src, dst, kind)
    return list(bag.values())


def build_task_dependency_graph(
    findings: Optional[Sequence[dict]] = None,
    *,
    edges: Optional[Sequence[dict]] = None,
    sync_holds: Optional[Sequence[dict]] = None,
    preemptions: Optional[Sequence[dict]] = None,
    migrations: Optional[Sequence[dict]] = None,
    priority_episodes: Optional[Sequence[dict]] = None,
    task: str = "",
    max_nodes: int = _GRAPH_MAX_NODES,
    max_edges: int = _GRAPH_MAX_EDGES,
) -> Dict[str, Any]:
    """Task/resource graph from BTF records, with finding-wording fallback."""
    want = str(task or "").strip()
    source = "btf"
    raw = [e for e in (edges or []) if isinstance(e, dict) and e.get("from") and e.get("to")]
    if not raw:
        raw = collect_dependency_edges(
            sync_holds=sync_holds,
            preemptions=preemptions,
            migrations=migrations,
            priority_episodes=priority_episodes,
        )
    if not raw:
        raw = _edges_from_findings(findings)
        source = "findings"
    scoped = _filter_graph_neighborhood(raw, want)
    responsible = _responsible_tasks(scoped, want)
    capped = _cap_graph_edges(scoped, max_nodes=max_nodes, max_edges=max_edges)
    nodes: Dict[str, str] = {}
    for e in capped:
        nodes.setdefault(e["from"], e.get("from_type") or _node_type(e["from"]))
        nodes.setdefault(e["to"], e.get("to_type") or _node_type(e["to"]))
    mermaid = "flowchart LR\n"
    names = list(nodes.keys())
    for i, name in enumerate(names):
        mermaid += f'  N{i}["{name[:40]}"]\n'
    ids = {name: f"N{i}" for i, name in enumerate(names)}
    for e in capped:
        a, b = ids.get(e["from"]), ids.get(e["to"])
        if a and b and a != b:
            mermaid += f"  {a} -->|{e['kind']}| {b}\n"
    if not nodes:
        mermaid += '  empty["No dependency nodes"]\n'
    focus = want or (next(iter(nodes), ""))
    extra = ""
    if responsible:
        extra = f"; {len(responsible)} task(s) upstream of {focus}"
    origin = "BTF sync/preempt/migrate" if source == "btf" else "finding wording"
    return {
        "ok": True,
        "message": f"{len(nodes)} nodes, {len(capped)} edges ({origin}){extra}",
        "task": focus,
        "source": source,
        "nodes": [{"id": n, "type": t} for n, t in nodes.items()],
        "edges": capped,
        "responsible": responsible,
        "mermaid": mermaid,
        "disclaimer": (
            "BTF edges from sync holds, preemption chains, migrations, and "
            "priority inheritance in the current cursor (or full trace)."
            if source == "btf"
            else "Edges inferred from finding wording, not from the BTF wait graph."
        ),
    }


def decompose_response_time(
    findings: Optional[Sequence[dict]] = None,
    *,
    task: str = "",
) -> Dict[str, Any]:
    items = _items(findings)
    want = str(task or "").strip()
    buckets: Dict[str, float] = {k: 0.0 for k, _ in _BUCKETS}
    buckets["other"] = 0.0
    used = 0
    for f in items:
        name = _task_of(f)
        if want and name and want not in name and name not in want:
            if want.lower() not in _blob(f).lower():
                continue
        mag = _magnitude(f)
        buckets[_bucket_of(_blob(f))] += mag
        used += 1
    total = sum(buckets.values()) or 1.0
    parts = [
        {"bucket": k, "ms": round(v, 4), "pct": round(100.0 * v / total, 1)}
        for k, v in buckets.items() if v > 0
    ]
    parts.sort(key=lambda r: -r["pct"])
    leader = parts[0]["bucket"] if parts else "unknown"
    tree = [f"Response time ~ {total:.3f} (relative units)"]
    for p in parts:
        tree.append(f"  └─ +{p['pct']}% {p['bucket']}")
    return {
        "ok": True,
        "message": f"Dominant delay: {leader}" if parts else "No delay components",
        "task": want,
        "parts": parts,
        "tree": tree,
        "dominant": leader,
        "findings_used": used,
        "disclaimer": "Shares are relative magnitudes from finding text/metrics, not cycle-accurate.",
    }


def rank_root_causes(
    findings: Optional[Sequence[dict]] = None,
    *,
    hypotheses: Optional[Sequence[dict]] = None,
) -> Dict[str, Any]:
    items = _items(findings)
    hyps = [h for h in (hypotheses or []) if isinstance(h, dict)]
    ranked: List[dict] = []
    if hyps:
        for i, h in enumerate(hyps):
            text = str(h.get("hypothesis") or h.get("description") or "")
            score = 0.4 + 0.15 * min(_magnitude({"title": text}), 4)
            status = str(h.get("status") or "").lower()
            if status == "supported":
                score += 0.25
            elif status == "rejected":
                score -= 0.4
            overlap = sum(1 for f in items if _bucket_of(_blob(f)) == _bucket_of(text))
            score += 0.08 * overlap
            ranked.append({
                "id": str(h.get("id") or f"H{i + 1}"),
                "cause": text or str(h.get("id") or f"H{i + 1}"),
                "score": round(max(0.01, min(0.99, score)), 3),
                "source": "hypothesis",
            })
    else:
        by_bucket: Dict[str, float] = {}
        for f in items:
            b = _bucket_of(_blob(f))
            by_bucket[b] = by_bucket.get(b, 0) + _magnitude(f)
        total = sum(by_bucket.values()) or 1.0
        for b, v in sorted(by_bucket.items(), key=lambda kv: -kv[1]):
            ranked.append({
                "id": b,
                "cause": b.replace("_", " "),
                "score": round(v / total, 3),
                "source": "finding",
            })
    ranked.sort(key=lambda r: -float(r["score"]))
    leader = ranked[0]["cause"] if ranked else ""
    return {
        "ok": True,
        "message": f"Leading cause: {leader}" if leader else "No causes to rank",
        "ranked": ranked,
        "leader": ranked[0] if ranked else None,
    }


def verify_claim(
    claim: str = "",
    *,
    claim_type: str = "causal",
    subject: str = "",
    object: str = "",
    evidence: Optional[Sequence[Any]] = None,
    findings: Optional[Sequence[dict]] = None,
    cursor_lo: Optional[float] = None,
    cursor_hi: Optional[float] = None,
) -> Dict[str, Any]:
    text = str(claim or "").strip()
    subj = str(subject or "").strip()
    obj = str(object or "").strip()
    items = _items(findings)
    ev = []
    for e in evidence or []:
        if isinstance(e, (int, float)):
            ev.append(float(e))
        else:
            ev.extend(_jumps(str(e)))
            try:
                ev.append(float(str(e).replace("jump:", "")))
            except ValueError:
                pass
    blob = " ".join(_blob(f) for f in items).lower()
    checks: List[dict] = []

    def _add(name: str, ok: bool, detail: str) -> None:
        checks.append({"check": name, "ok": ok, "detail": detail})

    if subj:
        _add("subject", subj.lower() in blob or any(
            subj in _task_of(f) for f in items), f"subject {subj!r}")
    if obj:
        _add("object", obj.lower() in blob, f"object {obj!r}")
    if text:
        keys = [w for w in re.findall(r"[a-z]{4,}", text.lower()) if w not in (
            "this", "that", "with", "from", "task")]
        hit = sum(1 for k in keys if k in blob)
        _add("evidence_lookup", hit >= max(1, len(keys) // 3),
             f"{hit}/{len(keys) or 1} claim tokens in findings")
    in_window = True
    if cursor_lo is not None and cursor_hi is not None and ev:
        lo, hi = min(cursor_lo, cursor_hi), max(cursor_lo, cursor_hi)
        in_window = all(lo <= t <= hi for t in ev)
        _add("scope", in_window, "evidence times inside cursors")
    elif ev:
        _add("temporal", True, f"{len(ev)} jump times")
    contradicted = False
    if "mutex" in text.lower() and "migrat" in blob and "mutex" not in blob:
        contradicted = True
        _add("contradiction", False, "Findings emphasise migration, not mutex")
    oks = [c["ok"] for c in checks] or [False]
    if contradicted or not any(oks):
        verdict = "rejected"
    elif all(oks):
        verdict = "confirmed"
    else:
        verdict = "inconclusive"
    return {
        "ok": True,
        "message": verdict,
        "claim": text,
        "type": str(claim_type or "causal"),
        "subject": subj,
        "object": obj,
        "verdict": verdict,
        "checks": checks,
        "evidence_times": ev,
    }


def challenge_conclusion(
    conclusion: str = "",
    *,
    findings: Optional[Sequence[dict]] = None,
    hypotheses: Optional[Sequence[dict]] = None,
) -> Dict[str, Any]:
    items = _items(findings)
    conc = str(conclusion or "").strip()
    leader = _bucket_of(conc) if conc else (
        _bucket_of(_blob(items[0])) if items else "other")
    alts: List[str] = []
    seen = {leader}
    for f in items:
        b = _bucket_of(_blob(f))
        if b not in seen:
            seen.add(b)
            alts.append(b.replace("_", " "))
    for h in hypotheses or []:
        if not isinstance(h, dict):
            continue
        text = str(h.get("hypothesis") or "")
        if text and _bucket_of(text) not in seen:
            alts.append(text)
    missing = []
    if "mutex" in leader and not any("preempt" in _blob(f).lower() for f in items):
        missing.append("No preemption alternative was measured.")
    if items and not any(_time_of(f) is not None for f in items):
        missing.append("No jump:TIME on supporting findings.")
    why_not = alts[:4]
    return {
        "ok": True,
        "message": (
            f"Alternatives to {leader}: {', '.join(why_not)}"
            if why_not else f"No strong alternative to {leader}"
        ),
        "conclusion": conc,
        "leading": leader,
        "alternatives": why_not,
        "missing_evidence": missing,
        "why_not": why_not,
    }


def investigation_memory(
    action: str = "recall",
    *,
    record: Optional[dict] = None,
    findings: Optional[Sequence[dict]] = None,
    limit: int = 5,
) -> Dict[str, Any]:
    act = str(action or "recall").strip().lower()
    if act in ("store", "save", "add") and isinstance(record, dict):
        entry = dict(record)
        if findings and not entry.get("finding"):
            items = _items(findings)
            entry["finding"] = str((items[0] or {}).get("title") or "") if items else ""
        _MEMORY.append(entry)
        return {
            "ok": True,
            "message": f"Stored memory ({len(_MEMORY)} entries)",
            "entry": entry,
            "count": len(_MEMORY),
        }
    items = _items(findings)
    blob = " ".join(_blob(f) for f in items).lower()
    ranked: List[dict] = []
    for row in _MEMORY:
        text = " ".join(str(row.get(k) or "") for k in (
            "finding", "root_cause", "pattern", "fix")).lower()
        score = 0.0
        for tok in set(re.findall(r"[a-z]{4,}", blob)):
            if tok in text:
                score += 1.0
        ranked.append({**row, "score": round(score, 2)})
    ranked.sort(key=lambda r: -float(r.get("score") or 0))
    hits = [r for r in ranked if float(r.get("score") or 0) > 0][: max(1, int(limit))]
    return {
        "ok": True,
        "message": (
            f"Seen this pattern before ({len(hits)} hits)"
            if hits else "No similar memories"
        ),
        "matches": hits,
        "count": len(_MEMORY),
    }


def cluster_incidents(
    findings: Optional[Sequence[dict]] = None,
    *,
    window_ns: float = 1e6,
) -> Dict[str, Any]:
    items = _items(findings)
    try:
        win = float(window_ns)
    except (TypeError, ValueError):
        win = 1e6
    clusters: List[List[dict]] = []
    timed = sorted(
        [( _time_of(f), f) for f in items],
        key=lambda p: (p[0] is None, p[0] or 0),
    )
    current: List[dict] = []
    last_t: Optional[float] = None
    for t, f in timed:
        if t is None:
            clusters.append([f])
            continue
        if last_t is None or abs(t - last_t) > win:
            if current:
                clusters.append(current)
            current = [f]
        else:
            current.append(f)
        last_t = t
    if current:
        clusters.append(current)
    out = []
    for i, group in enumerate(clusters):
        tasks = sorted({_task_of(f) for f in group if _task_of(f)})
        out.append({
            "id": f"I{i + 1}",
            "size": len(group),
            "tasks": tasks,
            "titles": [str(f.get("title") or f.get("id") or "") for f in group[:6]],
        })
    out.sort(key=lambda r: -int(r["size"]))
    return {
        "ok": True,
        "message": f"{len(out)} incident cluster(s)",
        "incidents": out,
        "window_ns": win,
    }


def close_investigation(
    conclusion: str = "",
    *,
    findings: Optional[Sequence[dict]] = None,
    experiments: Optional[Sequence[dict]] = None,
    confidence: str = "",
) -> Dict[str, Any]:
    items = _items(findings)
    conc = str(conclusion or "").strip() or (
        str(items[0].get("title") or "") if items else "unspecified"
    )
    exps = [e for e in (experiments or []) if isinstance(e, dict)]
    closed = {
        "conclusion": conc,
        "confidence": str(confidence or "Medium"),
        "finding_count": len(items),
        "experiments": exps,
        "status": "closed",
        "next": "Record outcome / recapture trace if an experiment is still open.",
    }
    return {
        "ok": True,
        "message": f"Closed: {conc}",
        "case": closed,
    }


def analyze_distribution(
    values: Optional[Sequence[Any]] = None,
    *,
    findings: Optional[Sequence[dict]] = None,
    metric: str = "",
    source: str = "",
    task: str = "",
    truncated: bool = False,
) -> Dict[str, Any]:
    nums: List[float] = []
    src = str(source or "").strip().lower()
    for v in values or []:
        try:
            nums.append(float(v))
        except (TypeError, ValueError):
            continue
    if nums:
        src = src or "values"
    else:
        for f in _items(findings):
            nums.append(_magnitude(f))
        if nums:
            src = "findings"
    nums.sort()
    n = len(nums)
    if not n:
        return {"ok": False, "message": "No numeric samples"}

    def _pct(p: float) -> float:
        if n == 1:
            return nums[0]
        idx = min(n - 1, max(0, int(round((p / 100.0) * (n - 1)))))
        return nums[idx]

    mean = sum(nums) / n
    p50, p90, p95 = _pct(50), _pct(90), _pct(95)
    p99, p999 = _pct(99), _pct(99.9)
    tail = (p99 / p50) if p50 else 0.0
    stddev = 0.0
    if n >= 2:
        stddev = math.sqrt(sum((x - mean) ** 2 for x in nums) / (n - 1))
    cv = (stddev / mean) if mean else 0.0
    outliers = 0
    if stddev > 0:
        limit = mean + 3.0 * stddev
        outliers = sum(1 for x in nums if x > limit)
    outlier_rate = 100.0 * outliers / n
    if src == "findings":
        disclaimer = "Magnitudes from finding text, not BTF samples."
    elif src == "btf":
        kind = str(metric or "sample")
        disclaimer = (
            f"Percentiles from BTF {kind} samples in the current cursor "
            "(or full trace)."
        )
    else:
        disclaimer = "Caller-supplied samples."
    return {
        "ok": True,
        "message": (
            f"n={n} p50={p50:.4g} p90={p90:.4g} p95={p95:.4g} "
            f"p99={p99:.4g} p99.9={p999:.4g} cv={cv:.3g} "
            f"outliers={outlier_rate:.3g}%"
        ),
        "metric": str(metric or ""),
        "task": str(task or ""),
        "source": src or "values",
        "n": n,
        "mean": round(mean, 6),
        "stddev": round(stddev, 6),
        "cv": round(cv, 4),
        "p50": round(p50, 6),
        "p90": round(p90, 6),
        "p95": round(p95, 6),
        "p99": round(p99, 6),
        "p99.9": round(p999, 6),
        "tail_ratio": round(tail, 3),
        "outlier_rate": round(outlier_rate, 3),
        "min": round(nums[0], 6),
        "max": round(nums[-1], 6),
        "truncated": bool(truncated),
        "disclaimer": disclaimer,
    }


def _percentile(nums: Sequence[float], p: float) -> float:
    n = len(nums)
    if n == 1:
        return float(nums[0])
    idx = min(n - 1, max(0, int(round((p / 100.0) * (n - 1)))))
    return float(nums[idx])


def _in_window(t: float, lo: Optional[float], hi: Optional[float]) -> bool:
    if lo is not None and t < lo:
        return False
    if hi is not None and t > hi:
        return False
    return True


def collect_periodicity_times(
    times: Optional[Sequence[Any]] = None,
    *,
    findings: Optional[Sequence[dict]] = None,
    source: str = "",
    tick_times: Optional[Sequence[Any]] = None,
    sti_events: Optional[Sequence[dict]] = None,
    release_times: Optional[Sequence[Any]] = None,
    lo: Optional[float] = None,
    hi: Optional[float] = None,
) -> List[float]:
    """Pick timestamps for periodicity: explicit times, tick/STI, ISR/timer, releases, findings."""

    def _floats(rows: Optional[Sequence[Any]]) -> List[float]:
        out: List[float] = []
        for v in rows or []:
            try:
                n = float(v)
            except (TypeError, ValueError):
                continue
            if _in_window(n, lo, hi):
                out.append(n)
        return out

    src = str(source or "auto").strip().lower() or "auto"
    explicit = _floats(times)
    if explicit:
        return sorted(set(explicit))
    ticks = _floats(tick_times)
    if src in ("tick", "sti") or (src == "auto" and ticks):
        if ticks or src in ("tick", "sti"):
            return sorted(set(ticks))

    def _sti_match(*needles: str) -> List[float]:
        out: List[float] = []
        for ev in sti_events or []:
            if not isinstance(ev, dict):
                continue
            blob = " ".join(str(ev.get(k) or "") for k in (
                "target", "event", "note", "channel")).lower()
            if not any(n in blob for n in needles):
                continue
            try:
                n = float(ev.get("time") if ev.get("time") is not None else ev.get("ns"))
            except (TypeError, ValueError):
                continue
            if _in_window(n, lo, hi):
                out.append(n)
        return out

    if src == "isr":
        return sorted(set(_sti_match("isr", "interrupt")))
    if src == "timer":
        return sorted(set(_sti_match("timer")))
    if src == "release":
        return sorted(set(_floats(release_times)))
    if src == "auto":
        isr = _sti_match("isr", "interrupt")
        if isr:
            return sorted(set(isr))
        timer = _sti_match("timer")
        if timer:
            return sorted(set(timer))
        releases = _floats(release_times)
        if releases:
            return sorted(set(releases))
    found = []
    for f in _items(findings):
        t = _time_of(f)
        if t is not None and _in_window(t, lo, hi):
            found.append(t)
    return sorted(set(found))


def _classify_periodicity(
    expected: float,
    p50: float,
    p99: float,
    max_gap: float,
    cv: float,
    findings: Optional[Sequence[dict]] = None,
    durations: Optional[Sequence[float]] = None,
) -> str:
    blob = " ".join(_blob(f) for f in _items(findings)).lower()
    durs = [d for d in (durations or []) if isinstance(d, (int, float))]
    if len(durs) >= 3:
        dmean = sum(durs) / len(durs)
        dvar = sum((d - dmean) ** 2 for d in durs) / len(durs)
        dcv = (math.sqrt(dvar) / dmean) if dmean else 0.0
        if dcv > max(cv, 0.05) * 1.25:
            return "execution-time variation"
    if expected:
        drift = abs(p50 - expected) / expected
        if drift > 0.12 and cv < 0.08:
            return "period drift"
        if max_gap > max(expected * 2.0, p99 * 1.4 if p99 else 0):
            if any(k in blob for k in ("preempt", "migrat", "isr", "interrupt")):
                return "scheduler interference"
            return "release jitter"
    if cv >= 0.08:
        if any(k in blob for k in ("preempt", "migrat", "isr", "interrupt")):
            return "scheduler interference"
        return "release jitter"
    return "stable period"


def analyze_periodicity(
    times: Optional[Sequence[Any]] = None,
    *,
    findings: Optional[Sequence[dict]] = None,
    expected: Optional[float] = None,
    source: str = "",
    durations: Optional[Sequence[Any]] = None,
    tick_times: Optional[Sequence[Any]] = None,
    sti_events: Optional[Sequence[dict]] = None,
    release_times: Optional[Sequence[Any]] = None,
    lo: Optional[float] = None,
    hi: Optional[float] = None,
) -> Dict[str, Any]:
    ts = collect_periodicity_times(
        times, findings=findings, source=source, tick_times=tick_times,
        sti_events=sti_events, release_times=release_times, lo=lo, hi=hi,
    )
    if len(ts) < 3:
        return {
            "ok": False,
            "message": "Need ≥3 timestamps for periodicity",
            "n": len(ts),
            "source": str(source or "auto"),
        }
    gaps = [ts[i] - ts[i - 1] for i in range(1, len(ts))]
    gaps_sorted = sorted(gaps)
    mean = sum(gaps) / len(gaps)
    p50 = _percentile(gaps_sorted, 50)
    p99 = _percentile(gaps_sorted, 99)
    max_gap = gaps_sorted[-1]
    min_gap = gaps_sorted[0]
    try:
        exp = float(expected) if expected not in (None, "") else p50
    except (TypeError, ValueError):
        exp = p50
    if not exp:
        exp = mean
    rms = math.sqrt(sum((g - exp) ** 2 for g in gaps) / len(gaps))
    gap_std = math.sqrt(sum((g - mean) ** 2 for g in gaps) / len(gaps))
    p2p = max_gap - min_gap
    cv = (gap_std / mean) if mean else 0.0
    durs: List[float] = []
    for v in durations or []:
        try:
            durs.append(float(v))
        except (TypeError, ValueError):
            continue
    kind = _classify_periodicity(
        exp, p50, p99, max_gap, cv, findings=findings, durations=durs)
    return {
        "ok": True,
        "message": (
            f"Expected period: {exp:.4g}  Measured p50={p50:.4g} "
            f"p99={p99:.4g} max={max_gap:.4g}  Jitter RMS={rms:.4g} "
            f"peak-to-peak={p2p:.4g}  ({kind})"
        ),
        "n": len(ts),
        "source": str(source or "auto"),
        "expected": round(exp, 6),
        "period": round(mean, 6),
        "p50": round(p50, 6),
        "p99": round(p99, 6),
        "max": round(max_gap, 6),
        "jitter": round(rms, 6),
        "rms": round(rms, 6),
        "peak_to_peak": round(p2p, 6),
        "cv": round(cv, 4),
        "min_gap": round(min_gap, 6),
        "max_gap": round(max_gap, 6),
        "kind": kind,
        "disclaimer": (
            "Heuristic on inter-arrival gaps (tick/STI/ISR/timer/releases/"
            "findings), not a kernel period timer."
        ),
    }


def summarize_investigation_context(
    findings: Optional[Sequence[dict]] = None,
    *,
    hypotheses: Optional[Sequence[dict]] = None,
    tools_run: Optional[Sequence[str]] = None,
    conclusion: str = "",
) -> Dict[str, Any]:
    items = _items(findings)
    hyps = [h for h in (hypotheses or []) if isinstance(h, dict)]
    tools = [str(t) for t in (tools_run or [])]
    titles = [str(f.get("title") or f.get("id") or "") for f in items[:8]]
    hyp_txt = [str(h.get("hypothesis") or h.get("id") or "") for h in hyps[:6]]
    summary = {
        "findings": titles,
        "hypotheses": hyp_txt,
        "tools_run": tools,
        "conclusion": str(conclusion or ""),
        "finding_count": len(items),
    }
    return {
        "ok": True,
        "message": (
            f"{len(items)} findings, {len(hyps)} hypotheses, {len(tools)} tools"
        ),
        "summary": summary,
    }


def simulate_schedule(
    changes: Optional[dict] = None,
    *,
    findings: Optional[Sequence[dict]] = None,
) -> Dict[str, Any]:
    """LEVEL 1 heuristic replay only — not an RTOS scheduler."""
    decomp = decompose_response_time(findings)
    ch = changes if isinstance(changes, dict) else {}
    predicted = dict(decomp)
    predicted["level"] = 1
    predicted["changes"] = ch
    predicted["ok"] = True
    predicted["message"] = (
        "LEVEL 1 heuristic replay only — not an RTOS scheduler."
    )
    predicted["disclaimer"] = predicted["message"]
    return predicted
