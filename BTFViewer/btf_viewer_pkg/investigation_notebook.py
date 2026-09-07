"""Investigation Bookmarks and Evidence Chain — deterministic model + serialisation.

Lockstep with ``web/src/utils/investigationNotebook.js``.

An *Investigation* preserves the reasoning behind a trace analysis: typed
bookmarks (observation / hypothesis / supporting / contradicting / verification /
conclusion), links between them, a conclusion, and open questions. Bookmarks
reference **stable identifiers** (a finding ``rule_id``, a metric/section name,
an entity, a time range) rather than copied display text alone, so a report
stays navigable after the underlying trace or statistics change — and stale
references are detectable.

Everything here is a pure function of its inputs. User-authored text
(``title`` / ``note`` / ``conclusion``) is never merged into measured data.
"""
from __future__ import annotations

import hashlib
import json
import re
from typing import Any, Dict, List, Optional, Sequence

INVESTIGATION_SCHEMA = "btf-viewer-investigation/1"

# --- Bookmark types --------------------------------------------------------
BM_OBSERVATION = "observation"
BM_HYPOTHESIS = "hypothesis"
BM_SUPPORTING = "supporting"
BM_CONTRADICTING = "contradicting"
BM_VERIFICATION = "verification"
BM_CONCLUSION = "conclusion"
BOOKMARK_TYPES = (
    BM_OBSERVATION, BM_HYPOTHESIS, BM_SUPPORTING,
    BM_CONTRADICTING, BM_VERIFICATION, BM_CONCLUSION,
)
BOOKMARK_TYPE_LABELS = {
    BM_OBSERVATION: "Observation",
    BM_HYPOTHESIS: "Hypothesis",
    BM_SUPPORTING: "Supporting evidence",
    BM_CONTRADICTING: "Contradicting evidence",
    BM_VERIFICATION: "Verification step",
    BM_CONCLUSION: "Conclusion",
}
# For the "clearly separate facts, hypotheses, contradictory evidence and
# conclusions" requirement of the HTML export.
FACT_TYPES = (BM_OBSERVATION, BM_SUPPORTING, BM_VERIFICATION)
INTERPRETATION_TYPES = (BM_HYPOTHESIS, BM_CONCLUSION)

# --- Reference kinds -----------------------------------------------------
REF_FINDING = "finding"
REF_METRIC = "metric"
REF_ENTITY = "entity"
REF_RANGE = "range"
REF_EVIDENCE = "evidence"
REF_KINDS = (REF_FINDING, REF_METRIC, REF_ENTITY, REF_RANGE, REF_EVIDENCE)

# --- Link relations ----------------------------------------------------
LINK_RELATIONS = ("supports", "contradicts", "verifies", "concludes", "relates")
# Which link relations a reviewer follows backwards from a conclusion to reach
# its evidence.
_CHAIN_RELATIONS = ("supports", "verifies", "contradicts", "concludes", "relates")

_SLUG_RE = re.compile(r"[^a-z0-9]+")


def _slug(text: str, used: set, prefix: str = "bm") -> str:
    base = _SLUG_RE.sub("-", str(text or "").lower()).strip("-")[:40] or prefix
    cand = base
    n = 2
    while cand in used:
        cand = f"{base}-{n}"
        n += 1
    used.add(cand)
    return cand


# ---------------------------------------------------------------------------
# Trace identity
# ---------------------------------------------------------------------------
def trace_identity(trace: Any, filename: str = "") -> Dict[str, Any]:
    """Stable fingerprint of a parsed trace for broken-reference detection."""
    if trace is None:
        return {"file": str(filename or ""), "hash": "", "time_scale": "",
                "event_count": 0, "span": None}
    segs = list(getattr(trace, "segments", None) or [])
    sti = list(getattr(trace, "sti_events", None) or [])
    t_min = getattr(trace, "time_min", None)
    t_max = getattr(trace, "time_max", None)
    h = hashlib.sha256()
    h.update(str(getattr(trace, "time_scale", "")).encode())
    h.update(f"|{t_min}|{t_max}|{len(segs)}|{len(sti)}".encode())
    for name in sorted(str(x) for x in (getattr(trace, "tasks", None) or []))[:200]:
        h.update(b"|")
        h.update(name.encode())
    return {
        "file": str(filename or ""),
        "hash": h.hexdigest()[:16],
        "time_scale": str(getattr(trace, "time_scale", "")),
        "event_count": len(segs) + len(sti),
        "span": ({"start": int(t_min), "end": int(t_max)}
                 if t_min is not None and t_max is not None else None),
    }


# ---------------------------------------------------------------------------
# Construction / editing (each returns a NEW investigation dict)
# ---------------------------------------------------------------------------
def new_investigation(
    *,
    title: str = "",
    trace_identity: Optional[Dict[str, Any]] = None,  # noqa: A002 - domain term
    analysis_range: Optional[Dict[str, int]] = None,
) -> Dict[str, Any]:
    rng = None
    if isinstance(analysis_range, dict) and analysis_range.get("start") is not None:
        rng = {"start": int(analysis_range["start"]), "end": int(analysis_range["end"])}
    return {
        "schema": INVESTIGATION_SCHEMA,
        "title": str(title or "").strip(),
        "trace_identity": dict(trace_identity or {}),
        "analysis_range": rng,
        "bookmarks": [],
        "links": [],
        "conclusion": "",
        "unresolved_questions": [],
        "next_seq": 1,
    }


def _clone(inv: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    if not isinstance(inv, dict):
        return new_investigation()
    out = dict(inv)
    out["bookmarks"] = [dict(b) for b in (inv.get("bookmarks") or [])]
    for b in out["bookmarks"]:
        b["refs"] = [dict(r) for r in (b.get("refs") or [])]
    out["links"] = [dict(link) for link in (inv.get("links") or [])]
    out["unresolved_questions"] = list(inv.get("unresolved_questions") or [])
    out["trace_identity"] = dict(inv.get("trace_identity") or {})
    return out


def normalize_ref(ref: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    if not isinstance(ref, dict):
        return None
    kind = str(ref.get("kind") or "").strip().lower()
    if kind not in REF_KINDS:
        return None
    out: Dict[str, Any] = {"kind": kind, "label": str(ref.get("label") or "").strip()}
    if kind == REF_FINDING:
        out["rule_id"] = str(ref.get("rule_id") or ref.get("id") or "").strip()
    elif kind == REF_METRIC:
        out["metric"] = str(ref.get("metric") or ref.get("label") or "").strip()
    elif kind == REF_ENTITY:
        out["entity"] = str(ref.get("entity") or ref.get("label") or "").strip()
    elif kind in (REF_RANGE, REF_EVIDENCE):
        rng = ref.get("range")
        if isinstance(rng, dict) and rng.get("start") is not None and rng.get("end") is not None:
            out["range"] = {"start": int(rng["start"]), "end": int(rng["end"])}
        if ref.get("time") is not None:
            try:
                out["time"] = int(float(ref["time"]))
            except (TypeError, ValueError):
                pass
    return out


def add_bookmark(
    inv: Optional[Dict[str, Any]],
    *,
    type: str,  # noqa: A002 - matches spec ("Bookmark Types")
    title: str,
    note: str = "",
    refs: Optional[Sequence[Dict[str, Any]]] = None,
    bookmark_id: str = "",
) -> Dict[str, Any]:
    out = _clone(inv)
    btype = str(type or "").strip().lower()
    if btype not in BOOKMARK_TYPES:
        btype = BM_OBSERVATION
    used = {str(b.get("id")) for b in out["bookmarks"]}
    bid = str(bookmark_id or "").strip()
    if not bid or bid in used:
        bid = _slug(f"{btype}-{title}", used)
    else:
        used.add(bid)
    seq = int(out.get("next_seq") or 1)
    out["next_seq"] = seq + 1
    clean_refs = [r for r in (normalize_ref(x) for x in (refs or [])) if r]
    out["bookmarks"].append({
        "id": bid,
        "type": btype,
        "title": str(title or "").strip() or BOOKMARK_TYPE_LABELS[btype],
        "note": str(note or ""),
        "refs": clean_refs,
        "seq": seq,
    })
    return out


def update_bookmark(
    inv: Optional[Dict[str, Any]],
    bookmark_id: str,
    **changes: Any,
) -> Dict[str, Any]:
    out = _clone(inv)
    bid = str(bookmark_id or "").strip()
    for b in out["bookmarks"]:
        if str(b.get("id")) != bid:
            continue
        if "type" in changes:
            t = str(changes["type"] or "").strip().lower()
            if t in BOOKMARK_TYPES:
                b["type"] = t
        if "title" in changes:
            b["title"] = str(changes["title"] or "").strip() or b["title"]
        if "note" in changes:
            b["note"] = str(changes["note"] or "")
        if "refs" in changes:
            b["refs"] = [r for r in (normalize_ref(x) for x in (changes["refs"] or [])) if r]
        break
    return out


def remove_bookmark(inv: Optional[Dict[str, Any]], bookmark_id: str) -> Dict[str, Any]:
    out = _clone(inv)
    bid = str(bookmark_id or "").strip()
    out["bookmarks"] = [b for b in out["bookmarks"] if str(b.get("id")) != bid]
    out["links"] = [
        link for link in out["links"]
        if str(link.get("from")) != bid and str(link.get("to")) != bid
    ]
    return out


def link_bookmarks(
    inv: Optional[Dict[str, Any]],
    from_id: str,
    to_id: str,
    relation: str = "relates",
) -> Dict[str, Any]:
    out = _clone(inv)
    a, b = str(from_id or "").strip(), str(to_id or "").strip()
    rel = str(relation or "relates").strip().lower()
    if rel not in LINK_RELATIONS:
        rel = "relates"
    ids = {str(x.get("id")) for x in out["bookmarks"]}
    if a == b or a not in ids or b not in ids:
        return out
    for link in out["links"]:
        if str(link.get("from")) == a and str(link.get("to")) == b:
            link["relation"] = rel
            return out
    out["links"].append({"from": a, "to": b, "relation": rel})
    return out


def unlink_bookmarks(
    inv: Optional[Dict[str, Any]], from_id: str, to_id: str
) -> Dict[str, Any]:
    out = _clone(inv)
    a, b = str(from_id or "").strip(), str(to_id or "").strip()
    out["links"] = [
        link for link in out["links"]
        if not (str(link.get("from")) == a and str(link.get("to")) == b)
    ]
    return out


def set_conclusion(inv: Optional[Dict[str, Any]], text: str) -> Dict[str, Any]:
    out = _clone(inv)
    out["conclusion"] = str(text or "").strip()
    return out


def add_unresolved_question(inv: Optional[Dict[str, Any]], text: str) -> Dict[str, Any]:
    out = _clone(inv)
    q = str(text or "").strip()
    if q and q not in out["unresolved_questions"]:
        out["unresolved_questions"].append(q)
    return out


def remove_unresolved_question(inv: Optional[Dict[str, Any]], text: str) -> Dict[str, Any]:
    out = _clone(inv)
    out["unresolved_questions"] = [
        q for q in out["unresolved_questions"] if q != str(text or "").strip()
    ]
    return out


# ---------------------------------------------------------------------------
# Undo / redo (snapshot stack — investigations are small)
# ---------------------------------------------------------------------------
def empty_notebook_history() -> Dict[str, Any]:
    return {"stack": [], "index": -1}


def _hist_index(out: Dict[str, Any]) -> int:
    raw = out.get("index")
    return -1 if raw is None else int(raw)


def push_notebook_state(
    history: Optional[Dict[str, Any]], inv: Dict[str, Any], *, limit: int = 100
) -> Dict[str, Any]:
    out = dict(history or empty_notebook_history())
    stack = [dict(s) for s in (out.get("stack") or [])]
    idx = _hist_index(out)
    if 0 <= idx < len(stack) - 1:
        stack = stack[: idx + 1]
    snap = json.loads(dump_investigation(inv))
    if stack and stack[-1] == snap:
        out["stack"] = stack
        out["index"] = len(stack) - 1
        return out
    stack.append(snap)
    if len(stack) > max(2, int(limit)):
        stack = stack[-int(limit):]
    out["stack"] = stack
    out["index"] = len(stack) - 1
    return out


def notebook_undo(history: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    out = dict(history or empty_notebook_history())
    out["index"] = max(0, _hist_index(out) - 1) if out.get("stack") else -1
    return out


def notebook_redo(history: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    out = dict(history or empty_notebook_history())
    stack = out.get("stack") or []
    out["index"] = min(len(stack) - 1, _hist_index(out) + 1)
    return out


def notebook_history_state(history: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    out = dict(history or empty_notebook_history())
    stack = list(out.get("stack") or [])
    idx = _hist_index(out)
    return {
        "can_undo": idx > 0,
        "can_redo": 0 <= idx < len(stack) - 1,
        "current": dict(stack[idx]) if 0 <= idx < len(stack) else None,
        "count": len(stack),
    }


# ---------------------------------------------------------------------------
# Broken-reference detection
# ---------------------------------------------------------------------------
def _ref_in_range(rng: Optional[Dict[str, int]], span: Optional[Dict[str, int]]) -> bool:
    if not isinstance(rng, dict) or not isinstance(span, dict):
        return True
    return int(rng["start"]) >= int(span["start"]) and int(rng["end"]) <= int(span["end"])


_ENTITY_LEAD_BRACKET_RE = re.compile(r"^\[[^\]]*\]")
_ENTITY_TAIL_ID_RE = re.compile(r"[\[(][^\])]*[\])]$")


def _entity_bare(name: Any) -> str:
    """Reduce a task label to its bare name for existence checks.

    ``[0/1]Worker`` / ``Worker[8]`` / ``Worker(0x9)`` and the merge key
    ``\\x001\\x00Worker`` all reduce to ``Worker`` — so an entity reference
    still resolves whichever decorated form it was stored in (Desktop vs. Web,
    pre/post Anonymize).
    """
    s = str(name or "")
    if s[:1] == "\x00":
        j = s.rfind("\x00")
        if j > 0:
            s = s[j + 1:]
    s = _ENTITY_LEAD_BRACKET_RE.sub("", s)
    s = _ENTITY_TAIL_ID_RE.sub("", s)
    return s.strip()


def _entity_vocabulary(trace: Any, known_entities: Optional[Sequence[str]]) -> set:
    """Every accepted spelling of every task / core in scope (decorated + bare)."""
    ents: set = set()
    for e in known_entities or []:
        ents.add(str(e))
        b = _entity_bare(e)
        if b:
            ents.add(b)
    if trace is not None:
        repr_map = getattr(trace, "task_repr", None)
        if isinstance(repr_map, dict) and repr_map:
            for mk, raw in repr_map.items():
                for form in (mk, raw):
                    ents.add(str(form))
                    b = _entity_bare(form)
                    if b:
                        ents.add(b)
        else:
            for mk in (getattr(trace, "tasks", None) or []):
                ents.add(str(mk))
                b = _entity_bare(mk)
                if b:
                    ents.add(b)
        for c in (getattr(trace, "core_names", None) or []):
            ents.add(str(c))
    return ents


def detect_broken_references(
    inv: Optional[Dict[str, Any]],
    *,
    trace: Any = None,
    known_rule_ids: Optional[Sequence[str]] = None,
    known_entities: Optional[Sequence[str]] = None,
    current_identity: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Report references that no longer resolve against the current trace.

    Returns ``{"stale_trace": bool, "issues": [{bookmark_id, ref_index,
    kind, reason}]}``.
    """
    inv = inv or new_investigation()
    issues: List[Dict[str, Any]] = []

    rule_ids = set(str(r) for r in (known_rule_ids or []))
    entities = _entity_vocabulary(trace, known_entities)
    span = None
    if current_identity and isinstance(current_identity.get("span"), dict):
        span = current_identity["span"]
    elif trace is not None:
        t_min = getattr(trace, "time_min", None)
        t_max = getattr(trace, "time_max", None)
        if t_min is not None and t_max is not None:
            span = {"start": int(t_min), "end": int(t_max)}

    stale_trace = False
    saved_id = inv.get("trace_identity") or {}
    if current_identity and saved_id.get("hash") and current_identity.get("hash"):
        stale_trace = saved_id["hash"] != current_identity["hash"]

    for b in inv.get("bookmarks") or []:
        bid = str(b.get("id") or "")
        for i, ref in enumerate(b.get("refs") or []):
            kind = str(ref.get("kind") or "")
            reason = ""
            if kind == REF_FINDING and rule_ids and ref.get("rule_id") not in rule_ids:
                reason = f"rule '{ref.get('rule_id')}' is no longer produced"
            elif kind == REF_ENTITY and entities:
                ent = str(ref.get("entity") or "")
                if ent not in entities and _entity_bare(ent) not in entities:
                    reason = f"entity '{ent}' is not in the trace"
            elif kind in (REF_RANGE, REF_EVIDENCE):
                if not _ref_in_range(ref.get("range"), span):
                    reason = "time range falls outside the trace span"
                t = ref.get("time")
                if t is not None and isinstance(span, dict) and not (
                    int(span["start"]) <= int(t) <= int(span["end"])
                ):
                    reason = "timestamp falls outside the trace span"
            if reason:
                issues.append({
                    "bookmark_id": bid, "ref_index": i,
                    "kind": kind, "reason": reason,
                })
    return {"stale_trace": stale_trace, "issues": issues}


# ---------------------------------------------------------------------------
# Conclusion → evidence chain
# ---------------------------------------------------------------------------
def _shared_ref(a: Dict[str, Any], b: Dict[str, Any]) -> bool:
    def keyset(bm):
        out = set()
        for r in bm.get("refs") or []:
            k = r.get("kind")
            if k == REF_FINDING and r.get("rule_id"):
                out.add(("finding", r["rule_id"]))
            elif k == REF_METRIC and r.get("metric"):
                out.add(("metric", r["metric"]))
            elif k == REF_ENTITY and r.get("entity"):
                out.add(("entity", r["entity"]))
        return out
    return bool(keyset(a) & keyset(b))


def conclusion_evidence_chains(inv: Optional[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """For every conclusion bookmark, the bookmarks that back it.

    A bookmark backs a conclusion when a link connects them (either direction)
    or they share a stable reference. Guarantees every conclusion is traceable
    to its evidence.
    """
    inv = inv or new_investigation()
    by_id = {str(b.get("id")): b for b in inv.get("bookmarks") or []}
    adj: Dict[str, set] = {bid: set() for bid in by_id}
    for link in inv.get("links") or []:
        a, b = str(link.get("from")), str(link.get("to"))
        if a in adj and b in adj:
            adj[a].add(b)
            adj[b].add(a)
    for a in by_id:
        for b in by_id:
            if a != b and _shared_ref(by_id[a], by_id[b]):
                adj[a].add(b)

    chains: List[Dict[str, Any]] = []
    for bid, bm in by_id.items():
        if bm.get("type") != BM_CONCLUSION:
            continue
        seen = {bid}
        queue = list(adj.get(bid, ()))
        support: List[Dict[str, Any]] = []
        while queue:
            nid = queue.pop(0)
            if nid in seen:
                continue
            seen.add(nid)
            nb = by_id.get(nid)
            if not nb:
                continue
            support.append({"id": nid, "type": nb.get("type"), "title": nb.get("title")})
            queue.extend(adj.get(nid, ()))
        support.sort(key=lambda x: (INTERPRETATION_TYPES.count(x["type"]), str(x["id"])))
        chains.append({
            "conclusion_id": bid,
            "title": bm.get("title"),
            "evidence": support,
            "grounded": bool(support),
        })
    return chains


# ---------------------------------------------------------------------------
# Serialisation
# ---------------------------------------------------------------------------
def dump_investigation(inv: Optional[Dict[str, Any]]) -> str:
    return json.dumps(load_investigation(inv), sort_keys=True, indent=2)


def load_investigation(raw: Any) -> Dict[str, Any]:
    """Coerce *raw* (dict or JSON text) to a valid investigation.

    Unknown top-level keys are preserved for forward compatibility.
    """
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except (ValueError, TypeError):
            raw = {}
    if not isinstance(raw, dict):
        raw = {}
    base = new_investigation(
        title=str(raw.get("title") or ""),
        trace_identity=raw.get("trace_identity") if isinstance(raw.get("trace_identity"), dict) else {},
        analysis_range=raw.get("analysis_range") if isinstance(raw.get("analysis_range"), dict) else None,
    )
    used: set = set()
    bookmarks: List[Dict[str, Any]] = []
    max_seq = 0
    for b in raw.get("bookmarks") or []:
        if not isinstance(b, dict):
            continue
        btype = str(b.get("type") or "").strip().lower()
        if btype not in BOOKMARK_TYPES:
            btype = BM_OBSERVATION
        bid = str(b.get("id") or "").strip()
        if not bid or bid in used:
            bid = _slug(f"{btype}-{b.get('title') or ''}", used)
        else:
            used.add(bid)
        try:
            seq = int(b.get("seq") or 0)
        except (TypeError, ValueError):
            seq = 0
        max_seq = max(max_seq, seq)
        bookmarks.append({
            "id": bid,
            "type": btype,
            "title": str(b.get("title") or "").strip() or BOOKMARK_TYPE_LABELS[btype],
            "note": str(b.get("note") or ""),
            "refs": [r for r in (normalize_ref(x) for x in (b.get("refs") or [])) if r],
            "seq": seq or (len(bookmarks) + 1),
        })
    bookmarks.sort(key=lambda b: (b["seq"], b["id"]))
    ids = {b["id"] for b in bookmarks}
    links = []
    seen_links: set = set()
    for link in raw.get("links") or []:
        if not isinstance(link, dict):
            continue
        a, b = str(link.get("from") or ""), str(link.get("to") or "")
        rel = str(link.get("relation") or "relates").strip().lower()
        if rel not in LINK_RELATIONS:
            rel = "relates"
        if a in ids and b in ids and a != b and (a, b) not in seen_links:
            seen_links.add((a, b))
            links.append({"from": a, "to": b, "relation": rel})

    out = dict(raw)  # preserve unknown keys
    out.update(base)
    out["bookmarks"] = bookmarks
    out["links"] = links
    out["conclusion"] = str(raw.get("conclusion") or "").strip()
    out["unresolved_questions"] = [
        str(q).strip() for q in (raw.get("unresolved_questions") or []) if str(q).strip()
    ]
    out["next_seq"] = max(int(base["next_seq"]), max_seq + 1)
    out["schema"] = INVESTIGATION_SCHEMA
    return out


# ---------------------------------------------------------------------------
# Bridge: build an Investigation from the Findings triage "case" list
# ---------------------------------------------------------------------------
def investigation_from_case(
    *,
    case_finding_ids: Sequence[str],
    findings: Sequence[Dict[str, Any]],
    trace_identity: Optional[Dict[str, Any]] = None,  # noqa: A002
    analysis_range: Optional[Dict[str, int]] = None,
    title: str = "",
) -> Dict[str, Any]:
    """Seed an Investigation from findings the user added to the case.

    Each cased finding becomes a *supporting evidence* bookmark that references
    the finding's stable ``rule_id``, its entities, and its range.
    """
    want = [str(x).strip() for x in (case_finding_ids or []) if str(x).strip()]
    by_id = {str(f.get("id") or ""): f for f in findings if isinstance(f, dict)}
    inv = new_investigation(
        title=title or "Investigation",
        trace_identity=trace_identity or {},
        analysis_range=analysis_range,
    )
    for fid in want:
        f = by_id.get(fid)
        if not f:
            continue
        refs: List[Dict[str, Any]] = [{
            "kind": REF_FINDING,
            "rule_id": str(f.get("rule_id") or fid),
            "label": str(f.get("title") or f.get("observation") or fid),
        }]
        for ent in f.get("entities") or []:
            refs.append({"kind": REF_ENTITY, "entity": str(ent), "label": str(ent)})
        rng = f.get("affected_range")
        if isinstance(rng, dict) and rng.get("start") is not None:
            refs.append({"kind": REF_RANGE, "range": rng, "label": "evidence window"})
        metric = str(f.get("inspect") or "").strip()
        if metric:
            refs.append({"kind": REF_METRIC, "metric": metric, "label": metric})
        inv = add_bookmark(
            inv,
            type=(BM_CONTRADICTING
                  if str(f.get("severity")) == "info" and "no findings" in str(f.get("title", "")).lower()
                  else BM_SUPPORTING),
            title=str(f.get("observation") or f.get("title") or fid),
            note=str(f.get("text") or ""),
            refs=refs,
        )
    return inv


_SEV_RANK = {"error": 0, "warning": 1, "info": 2}


def scaffold_investigation_from_findings(
    inv: Optional[Dict[str, Any]],
    *,
    findings: Optional[Sequence[Dict[str, Any]]] = None,
    cursor_range: Optional[Dict[str, int]] = None,
    limit: int = 8,
    include_info: bool = False,
) -> Dict[str, Any]:
    """Merge a starter structure into *inv* from the current analysis findings.

    Every actionable finding becomes an Observation (with finding / entity /
    range / metric refs); when the notebook was empty a Hypothesis and a
    Verification-step stub are appended so the evidence chain has somewhere to
    go. Findings already referenced by a bookmark are skipped — safe to re-run.
    """
    out = inv if isinstance(inv, dict) else new_investigation()
    was_empty = not (out.get("bookmarks") or [])

    already = set()
    for b in out.get("bookmarks") or []:
        for r in b.get("refs") or []:
            if r.get("kind") == REF_FINDING and r.get("rule_id"):
                already.add(str(r["rule_id"]))

    rows = [f for f in (findings or []) if isinstance(f, dict)]
    if not include_info:
        rows = [f for f in rows if str(f.get("severity") or "info") != "info"]
    rows.sort(key=lambda f: _SEV_RANK.get(str(f.get("severity")), 3))

    added = 0
    for f in rows:
        if added >= limit:
            break
        rule_id = str(f.get("rule_id") or f.get("id") or "").strip()
        if not rule_id or rule_id in already:
            continue
        already.add(rule_id)
        refs: List[Dict[str, Any]] = [{
            "kind": REF_FINDING, "rule_id": rule_id,
            "label": str(f.get("title") or rule_id),
        }]
        for ent in f.get("entities") or []:
            refs.append({"kind": REF_ENTITY, "entity": str(ent), "label": str(ent)})
        rng = f.get("affected_range")
        if not (isinstance(rng, dict) and rng.get("start") is not None):
            rng = cursor_range if isinstance(cursor_range, dict) and cursor_range.get("start") is not None else None
        if rng:
            refs.append({"kind": REF_RANGE,
                         "range": {"start": rng["start"], "end": rng["end"]},
                         "label": "evidence window"})
        metric = str(f.get("inspect") or f.get("inspect_href") or "").strip()
        if metric:
            refs.append({"kind": REF_METRIC, "metric": metric, "label": metric})
        out = add_bookmark(
            out, type=BM_OBSERVATION,
            title=str(f.get("title") or f.get("observation") or rule_id),
            note=str(f.get("text") or f.get("impact") or ""),
            refs=refs)
        added += 1

    if was_empty:
        out = add_bookmark(
            out, type=BM_HYPOTHESIS, title="Likely cause — edit this",
            note=("What single explanation best fits the observations above? "
                  "Link the observations that support it."))
        out = add_bookmark(
            out, type=BM_VERIFICATION, title="How to confirm — edit this",
            note=("Which measurement, cursor window, or experiment would confirm "
                  "or rule out the hypothesis?"))
    return out
