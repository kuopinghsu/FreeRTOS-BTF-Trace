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
from typing import Any, Dict, List, Optional, Sequence, Tuple

INVESTIGATION_SCHEMA = "btf-viewer-investigation/2"

# --- Durable investigation status (schema/2) -----------------------------
# One durable status only. The AI workflow *stage* is transient and must never
# be shown as a second Notebook status.
NB_STATUS_OPEN = "open"
NB_STATUS_NEEDS_EVIDENCE = "needs_evidence"
NB_STATUS_READY = "ready_to_conclude"
NB_STATUS_CLOSED = "closed"
NOTEBOOK_STATUSES = (
    NB_STATUS_OPEN, NB_STATUS_NEEDS_EVIDENCE, NB_STATUS_READY, NB_STATUS_CLOSED,
)
NOTEBOOK_STATUS_LABELS = {
    NB_STATUS_OPEN: "Open",
    NB_STATUS_NEEDS_EVIDENCE: "Needs evidence",
    NB_STATUS_READY: "Ready to conclude",
    NB_STATUS_CLOSED: "Closed",
}

# --- Six-section presentation ------------------------------------------
NB_SECTION_ORDER = (
    "question", "scope", "hypotheses", "evidence", "open_checks", "conclusion",
)
NB_SECTION_LABELS = {
    "question": "Question",
    "scope": "Scope",
    "hypotheses": "Hypotheses",
    "evidence": "Evidence",
    "open_checks": "Open checks",
    "conclusion": "Conclusion",
}

# Empty-state entry points (replace the old generic hint).
NB_EMPTY_FROM_FINDINGS = "Start from current Findings"
NB_EMPTY_BLANK = "Start a blank investigation"

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

# --- Structured evidence cards (schema/2, §8) --------------------------
# Where an evidence card came from.
EV_SOURCE_TIMELINE = "Timeline"
EV_SOURCE_STATISTICS = "Statistics"
EV_SOURCE_FINDINGS = "Analysis Findings"
EV_SOURCE_COMPARE = "Trace Compare"
EV_SOURCE_USER = "User note"
EV_SOURCE_AI = "AI suggestion"
EVIDENCE_SOURCES = (
    EV_SOURCE_TIMELINE, EV_SOURCE_STATISTICS, EV_SOURCE_FINDINGS,
    EV_SOURCE_COMPARE, EV_SOURCE_USER, EV_SOURCE_AI,
)
# How strong the claim is. "" = an unclassified user note.
EV_KIND_MEASURED = "measured"
EV_KIND_DERIVED = "derived"
EV_KIND_HEURISTIC = "heuristic"
EV_KIND_ESTIMATE = "estimate"
EVIDENCE_KINDS = (
    EV_KIND_MEASURED, EV_KIND_DERIVED, EV_KIND_HEURISTIC, EV_KIND_ESTIMATE,
)
EVIDENCE_KIND_LABELS = {
    EV_KIND_MEASURED: "Measured",
    EV_KIND_DERIVED: "Derived",
    EV_KIND_HEURISTIC: "Heuristic",
    EV_KIND_ESTIMATE: "Simulation / estimate",
    "": "User note",
}
EV_AUTHOR_USER = "user"
EV_AUTHOR_BTFVIEWER = "btfviewer"
EV_AUTHOR_AI = "ai"
EVIDENCE_AUTHORS = (EV_AUTHOR_USER, EV_AUTHOR_BTFVIEWER, EV_AUTHOR_AI)
# Only BTFViewer-supplied measured cards carry these; user edits and AI
# proposals must never change them.
EVIDENCE_PROTECTED_FIELDS = (
    "source", "kind", "author", "trace_id", "scope",
    "task", "core", "value", "unit",
)
# Evidence-bearing bookmark types (the ones the Evidence section renders).
EVIDENCE_BOOKMARK_TYPES = (BM_OBSERVATION, BM_SUPPORTING, BM_CONTRADICTING)


def _measured_ref(refs: Optional[Sequence[Dict[str, Any]]]) -> str:
    """The strongest measured-output ref kind on a bookmark, or ""."""
    kinds = {str(r.get("kind")) for r in (refs or []) if isinstance(r, dict)}
    if REF_FINDING in kinds:
        return EV_SOURCE_FINDINGS
    if REF_METRIC in kinds:
        return EV_SOURCE_STATISTICS
    if kinds & {REF_RANGE, REF_EVIDENCE}:
        return EV_SOURCE_TIMELINE
    return ""


def normalize_evidence_card(
    card: Optional[Dict[str, Any]],
    *,
    refs: Optional[Sequence[Dict[str, Any]]] = None,
) -> Optional[Dict[str, Any]]:
    """Coerce a raw evidence card to a valid one, enforcing provenance rules.

    - AI-authored or ``AI suggestion`` cards can never be ``measured``.
    - A ``measured`` kind is only kept when the card is BTFViewer/User authored
      *and* the bookmark references measured output (a finding / metric / range).
    - Source data fields are kept as-is; the editable text lives on the
      bookmark's ``note``.
    """
    if not isinstance(card, dict):
        return None
    src = str(card.get("source") or "").strip()
    if src not in EVIDENCE_SOURCES:
        src = _measured_ref(refs) or EV_SOURCE_USER
    author = str(card.get("author") or "").strip().lower()
    if author not in EVIDENCE_AUTHORS:
        author = EV_AUTHOR_AI if src == EV_SOURCE_AI else EV_AUTHOR_USER
    if src == EV_SOURCE_AI:
        author = EV_AUTHOR_AI
    kind = str(card.get("kind") or "").strip().lower()
    if kind not in EVIDENCE_KINDS:
        kind = ""
    if kind == EV_KIND_MEASURED and (
        author == EV_AUTHOR_AI or not _measured_ref(refs)
    ):
        # Never label AI prose or an unreferenced claim as Measured.
        kind = EV_KIND_DERIVED if author != EV_AUTHOR_AI else ""
    out: Dict[str, Any] = {
        "source": src,
        "kind": kind,
        "author": author,
        "trace_id": str(card.get("trace_id") or ""),
        "task": str(card.get("task") or ""),
        "core": str(card.get("core") or ""),
        "unit": str(card.get("unit") or ""),
        "hypothesis_id": str(card.get("hypothesis_id") or ""),
        "created_at": str(card.get("created_at") or ""),
        "updated_at": str(card.get("updated_at") or ""),
    }
    val = card.get("value")
    if isinstance(val, (int, float)) and not isinstance(val, bool):
        out["value"] = val
    else:
        try:
            out["value"] = float(val) if str(val).strip() != "" else None
        except (TypeError, ValueError):
            out["value"] = None
    sc = card.get("scope")
    if isinstance(sc, dict) and sc.get("start") is not None and sc.get("end") is not None:
        out["scope"] = {"start": int(sc["start"]), "end": int(sc["end"])}
    else:
        out["scope"] = None
    return out


def evidence_card_is_measured(card: Optional[Dict[str, Any]]) -> bool:
    return isinstance(card, dict) and card.get("kind") == EV_KIND_MEASURED


def guard_evidence_changes(
    card: Optional[Dict[str, Any]],
    changes: Optional[Dict[str, Any]],
) -> Tuple[Dict[str, Any], List[str]]:
    """Split proposed card ``changes`` into (allowed, rejected-field-names).

    Protected fields on a measured card are never mutable by a user edit or an
    AI proposal; a change that would set ``kind`` to ``measured`` is rejected
    unless the card already is.
    """
    ch = dict(changes or {})
    allowed: Dict[str, Any] = {}
    rejected: List[str] = []
    measured = evidence_card_is_measured(card)
    for key, val in ch.items():
        if key == "kind" and str(val).strip().lower() == EV_KIND_MEASURED and not measured:
            rejected.append(key)
            continue
        if measured and key in EVIDENCE_PROTECTED_FIELDS:
            rejected.append(key)
            continue
        allowed[key] = val
    return allowed, rejected


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
        "status": NB_STATUS_OPEN,
        "updated_at": "",
        "next_seq": 1,
    }


def _clone(inv: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    if not isinstance(inv, dict):
        return new_investigation()
    out = dict(inv)
    out["bookmarks"] = [dict(b) for b in (inv.get("bookmarks") or [])]
    for b in out["bookmarks"]:
        b["refs"] = [dict(r) for r in (b.get("refs") or [])]
        if isinstance(b.get("evidence"), dict):
            b["evidence"] = dict(b["evidence"])
            if isinstance(b["evidence"].get("scope"), dict):
                b["evidence"]["scope"] = dict(b["evidence"]["scope"])
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
    evidence: Optional[Dict[str, Any]] = None,
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
    row: Dict[str, Any] = {
        "id": bid,
        "type": btype,
        "title": str(title or "").strip() or BOOKMARK_TYPE_LABELS[btype],
        "note": str(note or ""),
        "refs": clean_refs,
        "seq": seq,
    }
    if evidence is not None and btype in EVIDENCE_BOOKMARK_TYPES:
        card = normalize_evidence_card(evidence, refs=clean_refs)
        if card is not None:
            row["evidence"] = card
    out["bookmarks"].append(row)
    return out


def add_evidence(
    inv: Optional[Dict[str, Any]],
    *,
    title: str,
    note: str = "",
    role: str = BM_SUPPORTING,
    source: str = EV_SOURCE_USER,
    kind: str = "",
    author: str = EV_AUTHOR_USER,
    refs: Optional[Sequence[Dict[str, Any]]] = None,
    task: str = "",
    core: str = "",
    value: Any = None,
    unit: str = "",
    scope: Optional[Dict[str, int]] = None,
    trace_id: str = "",
    hypothesis_id: str = "",
    created_at: str = "",
    bookmark_id: str = "",
) -> Dict[str, Any]:
    """Add a structured evidence card (a bookmark with an ``evidence`` dict).

    Source data (``kind`` / ``value`` / ``unit`` / ``task`` / ``core`` /
    ``scope`` / ``trace_id`` / ``refs``) is stored separately from the editable
    explanation (``note``). Provenance rules are enforced by
    :func:`normalize_evidence_card`.
    """
    r = str(role or "").strip().lower()
    if r not in EVIDENCE_BOOKMARK_TYPES:
        r = BM_SUPPORTING
    return add_bookmark(
        inv, type=r, title=title, note=note, refs=refs, bookmark_id=bookmark_id,
        evidence={
            "source": source, "kind": kind, "author": author, "task": task,
            "core": core, "value": value, "unit": unit, "scope": scope,
            "trace_id": trace_id, "hypothesis_id": hypothesis_id,
            "created_at": created_at, "updated_at": created_at,
        },
    )


def update_evidence_explanation(
    inv: Optional[Dict[str, Any]], bookmark_id: str, note: str,
    *, updated_at: str = "",
) -> Dict[str, Any]:
    """Edit *only* the explanation text of an evidence card — never source data."""
    out = _clone(inv)
    bid = str(bookmark_id or "").strip()
    for b in out["bookmarks"]:
        if str(b.get("id")) != bid:
            continue
        b["note"] = str(note or "")
        if isinstance(b.get("evidence"), dict) and updated_at:
            b["evidence"]["updated_at"] = str(updated_at)
        break
    return out


def apply_evidence_edit(
    inv: Optional[Dict[str, Any]], bookmark_id: str,
    changes: Optional[Dict[str, Any]], *, updated_at: str = "",
) -> Tuple[Dict[str, Any], List[str]]:
    """Merge proposed card ``changes`` for one evidence bookmark.

    Protected fields on a measured card (and any attempt to set ``kind`` to
    ``measured``) are dropped; the returned list names the rejected fields so
    the caller can surface "measured data not changed".
    """
    out = _clone(inv)
    bid = str(bookmark_id or "").strip()
    rejected: List[str] = []
    for b in out["bookmarks"]:
        if str(b.get("id")) != bid:
            continue
        card = b.get("evidence") if isinstance(b.get("evidence"), dict) else {}
        allowed, rejected = guard_evidence_changes(card, changes)
        if "note" in allowed:
            b["note"] = str(allowed.pop("note") or "")
        if allowed:
            merged = dict(card)
            merged.update(allowed)
            b["evidence"] = normalize_evidence_card(merged, refs=b.get("refs"))
        if isinstance(b.get("evidence"), dict) and updated_at:
            b["evidence"]["updated_at"] = str(updated_at)
        break
    return out, rejected


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
# Durable status (schema/2)
# ---------------------------------------------------------------------------
def derive_status(inv: Optional[Dict[str, Any]]) -> str:
    """Best-effort durable status for a schema/1 investigation being upgraded.

    Never returns ``closed`` — closing an investigation is an explicit act.
    """
    inv = inv if isinstance(inv, dict) else {}
    bms = inv.get("bookmarks") or []
    types = [str(b.get("type") or "") for b in bms if isinstance(b, dict)]
    has_hypothesis = BM_HYPOTHESIS in types
    has_evidence = any(t in (BM_SUPPORTING, BM_VERIFICATION) for t in types)
    has_conclusion = bool(str(inv.get("conclusion") or "").strip()) or (
        BM_CONCLUSION in types
    )
    has_open = bool(inv.get("unresolved_questions"))
    if has_conclusion:
        return NB_STATUS_READY
    if has_hypothesis and not has_evidence:
        return NB_STATUS_NEEDS_EVIDENCE
    if has_open:
        return NB_STATUS_NEEDS_EVIDENCE
    return NB_STATUS_OPEN


def set_status(
    inv: Optional[Dict[str, Any]], status: str, *, updated_at: str = "",
) -> Dict[str, Any]:
    out = _clone(inv)
    s = str(status or "").strip().lower()
    out["status"] = s if s in NOTEBOOK_STATUSES else NB_STATUS_OPEN
    if updated_at:
        out["updated_at"] = str(updated_at)
    return out


def touch_investigation(inv: Optional[Dict[str, Any]], updated_at: str) -> Dict[str, Any]:
    """Stamp the caller-supplied last-updated time (kept pure — no clock here)."""
    out = _clone(inv)
    out["updated_at"] = str(updated_at or "")
    return out


def migrate_investigation(inv: Dict[str, Any]) -> Dict[str, Any]:
    """Bring a normalised investigation dict up to the current schema.

    Keeps every existing bookmark, link, question and conclusion. A schema/1
    payload (no ``status``) gets a derived durable status; a valid stored
    status is preserved. A transient ``workflow_stage`` key, if present, is
    left untouched — it is never promoted to the Notebook status.
    """
    stored = str(inv.get("status") or "").strip().lower()
    inv["status"] = stored if stored in NOTEBOOK_STATUSES else derive_status(inv)
    inv["updated_at"] = str(inv.get("updated_at") or "")
    # Wrap legacy evidence bookmarks (schema/1) in a provenance card, keeping
    # every id / ref / note. Provenance is inferred conservatively: a bookmark
    # that references measured BTFViewer output is Measured; a bare note is a
    # user note. Never retroactively AI-attributed.
    for b in inv.get("bookmarks") or []:
        if not isinstance(b, dict):
            continue
        if b.get("type") not in EVIDENCE_BOOKMARK_TYPES or isinstance(b.get("evidence"), dict):
            continue
        refs = b.get("refs") or []
        src = _measured_ref(refs) or EV_SOURCE_USER
        b["evidence"] = normalize_evidence_card(
            {
                "source": src,
                "kind": EV_KIND_MEASURED if src != EV_SOURCE_USER else "",
                "author": EV_AUTHOR_USER,
                "trace_id": str((inv.get("trace_identity") or {}).get("hash") or ""),
            },
            refs=refs,
        )
    inv["schema"] = INVESTIGATION_SCHEMA
    return inv


# ---------------------------------------------------------------------------
# Six-section presentation (pure projection of the stored investigation)
# ---------------------------------------------------------------------------
def _evidence_kind(bookmark: Dict[str, Any]) -> str:
    """Coarse provenance for an evidence bookmark. §8 refines this into cards;
    here a bookmark that points at measured BTFViewer output is ``measured``,
    everything else is a plain ``note``."""
    for r in bookmark.get("refs") or []:
        if str(r.get("kind")) in (REF_FINDING, REF_METRIC, REF_RANGE):
            return "measured"
    return "note"


def _hypothesis_status(inv: Dict[str, Any], bid: str) -> str:
    rels = {
        str(link.get("relation"))
        for link in inv.get("links") or []
        if str(link.get("to")) == bid or str(link.get("from")) == bid
    }
    if "contradicts" in rels:
        return "contradicted"
    if rels & {"supports", "verifies"}:
        return "supported"
    return "open"


def _scope_summary(inv: Dict[str, Any]) -> str:
    rng = inv.get("analysis_range")
    if isinstance(rng, dict) and rng.get("start") is not None:
        return f"{int(rng['start'])}–{int(rng['end'])}"
    return "Full trace"


def _stale_bookmark_ids(broken: Optional[Dict[str, Any]]) -> set:
    if not isinstance(broken, dict):
        return set()
    return {
        str(i.get("bookmark_id"))
        for i in (broken.get("issues") or [])
        if isinstance(i, dict) and i.get("bookmark_id")
    }


def _evidence_is_stale(
    bid: str, nav: Dict[str, Any], stale_ids: set, broken: Optional[Dict[str, Any]],
) -> bool:
    if bid in stale_ids:
        return True
    # A whole-trace change makes every trace-bound reference (a time / range /
    # finding / metric) unverifiable — flag it, never hide it.
    if isinstance(broken, dict) and broken.get("stale_trace"):
        return bool(nav)
    return False


def evidence_nav_targets(bookmark: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """Resolvable navigation targets for one evidence bookmark — no scope change.

    Returns ``{jump: TIME}`` / ``{range: [LO, HI]}`` / ``{stats_metric: NAME}``
    only for refs that carry a target; an empty dict when nothing resolves.
    """
    out: Dict[str, Any] = {}
    for r in (bookmark or {}).get("refs") or []:
        if not isinstance(r, dict):
            continue
        if r.get("time") is not None and "jump" not in out:
            out["jump"] = int(r["time"])
        rng = r.get("range")
        if isinstance(rng, dict) and rng.get("start") is not None and "range" not in out:
            out["range"] = [int(rng["start"]), int(rng["end"])]
        if str(r.get("kind")) == REF_METRIC and r.get("metric") and "stats_metric" not in out:
            out["stats_metric"] = str(r["metric"])
        if str(r.get("kind")) == REF_FINDING and r.get("rule_id") and "finding" not in out:
            out["finding"] = str(r["rule_id"])
    return out


def investigation_sections(
    inv: Optional[Dict[str, Any]],
    *,
    broken: Optional[Dict[str, Any]] = None,
) -> List[Dict[str, Any]]:
    """Project a stored investigation onto the six report sections, in order.

    Purely derived from existing fields — no data is invented or relabelled as
    measured. Existing bookmark ids / links / conclusions are preserved
    verbatim in ``bookmark_id`` / ``refs`` on each item. Evidence items carry
    the full provenance ``card`` and a ``stale`` flag (from an optional
    :func:`detect_broken_references` result); stale evidence stays visible.
    """
    inv = load_investigation(inv)
    bms = inv.get("bookmarks") or []
    ident = inv.get("trace_identity") or {}
    stale = _stale_bookmark_ids(broken)

    scope_items: List[Dict[str, Any]] = []
    if ident.get("file"):
        scope_items.append({"kind": "trace", "text": str(ident["file"])})
    scope_items.append({"kind": "range", "text": _scope_summary(inv)})
    if ident.get("time_scale"):
        scope_items.append({"kind": "unit", "text": str(ident["time_scale"])})

    hyp_items = [
        {
            "bookmark_id": b["id"], "text": b["title"], "note": b["note"],
            "refs": b["refs"], "status": _hypothesis_status(inv, b["id"]),
        }
        for b in bms if b["type"] == BM_HYPOTHESIS
    ]
    evidence_items = []
    for b in bms:
        if b["type"] not in EVIDENCE_BOOKMARK_TYPES:
            continue
        card = b.get("evidence") if isinstance(b.get("evidence"), dict) else None
        nav = evidence_nav_targets(b)
        evidence_items.append({
            "bookmark_id": b["id"], "text": b["title"], "note": b["note"],
            "refs": b["refs"],
            "role": (
                "supporting" if b["type"] == BM_SUPPORTING
                else "contradicting" if b["type"] == BM_CONTRADICTING
                else "observation"
            ),
            "kind": (card or {}).get("kind", _evidence_kind(b)),
            "card": card,
            "stale": _evidence_is_stale(b["id"], nav, stale, broken),
            "nav": nav,
        })
    open_items = [
        {"source": "question", "text": q}
        for q in inv.get("unresolved_questions") or []
    ] + [
        {
            "source": "verification", "bookmark_id": b["id"], "text": b["title"],
            "note": b["note"], "refs": b["refs"],
        }
        for b in bms if b["type"] == BM_VERIFICATION
    ]
    conclusion_items: List[Dict[str, Any]] = []
    if str(inv.get("conclusion") or "").strip():
        conclusion_items.append({"kind": "verdict", "text": inv["conclusion"]})
    for b in bms:
        if b["type"] == BM_CONCLUSION:
            conclusion_items.append({
                "kind": "verdict", "bookmark_id": b["id"], "text": b["title"],
                "note": b["note"], "refs": b["refs"],
            })
    verified = sum(1 for b in bms if b["type"] == BM_VERIFICATION)
    conclusion_items.append({
        "kind": "verification_state",
        "text": (
            f"{verified} verification step(s) recorded"
            if verified else "No verification steps recorded"
        ),
    })

    by_id = {
        "question": [{"text": inv["title"]}] if inv.get("title") else [],
        "scope": scope_items,
        "hypotheses": hyp_items,
        "evidence": evidence_items,
        "open_checks": open_items,
        "conclusion": conclusion_items,
    }
    return [
        {"id": sid, "title": NB_SECTION_LABELS[sid], "items": by_id[sid]}
        for sid in NB_SECTION_ORDER
    ]


def investigation_header(
    inv: Optional[Dict[str, Any]],
    *,
    broken: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Compact header row for the Notebook — usable with AI disabled.

    ``broken`` is an optional :func:`detect_broken_references` result so the
    stale-reference count stays a pure function of its inputs.
    """
    inv = load_investigation(inv)
    secs = {s["id"]: s for s in investigation_sections(inv)}
    status = str(inv.get("status") or NB_STATUS_OPEN)
    ident = inv.get("trace_identity") or {}
    return {
        "status": status,
        "status_label": NOTEBOOK_STATUS_LABELS.get(status, "Open"),
        "trace": str(ident.get("file") or ""),
        "scope": _scope_summary(inv),
        "hypothesis_count": len(secs["hypotheses"]["items"]),
        "evidence_count": len(secs["evidence"]["items"]),
        "open_check_count": len(secs["open_checks"]["items"]),
        "stale_ref_count": len((broken or {}).get("issues") or []),
        "updated_at": str(inv.get("updated_at") or ""),
    }


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
        clean_refs = [r for r in (normalize_ref(x) for x in (b.get("refs") or [])) if r]
        row: Dict[str, Any] = {
            "id": bid,
            "type": btype,
            "title": str(b.get("title") or "").strip() or BOOKMARK_TYPE_LABELS[btype],
            "note": str(b.get("note") or ""),
            "refs": clean_refs,
            "seq": seq or (len(bookmarks) + 1),
        }
        if isinstance(b.get("evidence"), dict) and btype in EVIDENCE_BOOKMARK_TYPES:
            card = normalize_evidence_card(b["evidence"], refs=clean_refs)
            if card is not None:
                row["evidence"] = card
        bookmarks.append(row)
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
    # base (from new_investigation) carries default status/updated_at; keep any
    # stored values so migrate_investigation can honour an explicit status.
    out["status"] = raw.get("status") or ""
    out["updated_at"] = str(raw.get("updated_at") or "")
    out["next_seq"] = max(int(base["next_seq"]), max_seq + 1)
    out["schema"] = INVESTIGATION_SCHEMA
    return migrate_investigation(out)


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
