"""Collaborate-with-AI entry point + AI proposal review for the Investigation
Notebook (BTFVIEWER_DESIGN_CONSISTENCY_TODO §9, §10).

Pure functions. ``investigation_notebook`` stays AI-independent; this module is
the *only* place that turns AI output into **proposed** Notebook operations and
validates them against protected provenance before the user accepts. Nothing
here mutates durable investigation state on its own — ``apply_proposal`` is the
explicit-acceptance entry point and is never wired to run automatically.

Lockstep with ``web/src/utils/investigationAi.js``.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence, Tuple

from .investigation_notebook import (
    BM_CONCLUSION,
    BM_HYPOTHESIS,
    EVIDENCE_BOOKMARK_TYPES,
    EV_AUTHOR_AI,
    EV_KIND_MEASURED,
    LINK_RELATIONS,
    NB_STATUS_CLOSED,
    NOTEBOOK_STATUSES,
    add_evidence,
    guard_evidence_changes,
    investigation_header,
    investigation_sections,
    link_bookmarks,
    load_investigation,
    normalize_evidence_card,
    remove_bookmark,
    set_conclusion,
    set_status,
    update_evidence_explanation,
)

# ---------------------------------------------------------------------------
# §9 — one Notebook-level "Collaborate with AI" entry point
# ---------------------------------------------------------------------------
NB_AI_DISABLED_REASON = "Enable AI Assistant in Settings → AI"

NB_AI_ACTIONS: Tuple[Tuple[str, str, str], ...] = (
    ("review_investigation", "Review investigation",
     "Review this investigation. List unsupported claims, contradictions and "
     "missing evidence. Do not change anything — return findings only."),
    ("suggest_next_check", "Suggest next check",
     "Recommend exactly one evidence-producing action available in BTFViewer "
     "(a tool call or a Statistics/Timeline step) that would most advance this "
     "investigation. One action, with the reason."),
    ("draft_hypotheses", "Draft hypotheses",
     "Propose up to three hypotheses for the open question. Mark each 'open' — "
     "never 'supported'. Cite the evidence id(s) each rests on."),
    ("draft_conclusion", "Draft conclusion",
     "Draft a conclusion using only the accepted Notebook evidence. State "
     "limitations and the verification state. Cite the evidence ids used."),
    ("update_from_findings", "Update from Findings",
     "Propose evidence cards from the current deterministic Analysis Findings. "
     "Each card must reference the finding's rule_id; never label a card "
     "Measured unless it references measured BTFViewer output."),
    ("compare_trace", "Compare with another trace",
     "Compare with the other open trace. Baseline A is Trace A, Candidate B is "
     "Trace B; verdicts describe Candidate B versus Baseline A. Use the current "
     "Compare Scope."),
)
_NB_AI_ACTION_IDS = frozenset(a[0] for a in NB_AI_ACTIONS)
NB_AI_ACTION_LABELS = {a[0]: a[1] for a in NB_AI_ACTIONS}
NB_AI_ACTION_PROMPTS = {a[0]: a[2] for a in NB_AI_ACTIONS}


def nb_ai_action_reason(
    action_id: str,
    inv: Optional[Dict[str, Any]],
    *,
    ai_enabled: bool,
    has_second_trace: bool = False,
) -> str:
    """"" if the action is available, else why it is disabled."""
    if not ai_enabled:
        return NB_AI_DISABLED_REASON
    aid = str(action_id or "").strip()
    if aid == "compare_trace" and not has_second_trace:
        return "Open a second trace to compare"
    if aid == "draft_conclusion":
        secs = {s["id"]: s for s in investigation_sections(inv)}
        if not secs["evidence"]["items"]:
            return "Add evidence before drafting a conclusion"
    return ""


def collaborate_header(
    inv: Optional[Dict[str, Any]],
    *,
    broken: Optional[Dict[str, Any]] = None,
    selected_count: int = 0,
) -> Dict[str, Any]:
    """Compact context header for the AI panel while collaborating on a Notebook."""
    inv = load_investigation(inv)
    hdr = investigation_header(inv, broken=broken)
    stale = int(hdr.get("stale_ref_count") or 0)
    return {
        "investigation_title": str(inv.get("title") or "Untitled investigation"),
        "status_label": hdr["status_label"],
        "trace": hdr["trace"],
        "scope": hdr["scope"],
        "evidence_count": hdr["evidence_count"],
        "selected_count": int(selected_count or 0),
        "stale_warning": (
            f"{stale} reference(s) no longer resolve" if stale else ""
        ),
    }


def collaborate_context(
    inv: Optional[Dict[str, Any]],
    *,
    action: str = "",
    findings: Optional[Sequence[Dict[str, Any]]] = None,
    selected_evidence_ids: Optional[Sequence[str]] = None,
    broken: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """The exact Notebook content sent to the AI — the active investigation and
    the selected (or all) evidence, nothing else. The caller can show this to
    the user verbatim.
    """
    inv = load_investigation(inv)
    aid = str(action or "").strip()
    if aid and aid not in _NB_AI_ACTION_IDS:
        aid = ""
    sections = investigation_sections(inv, broken=broken)
    ev_items = next((s["items"] for s in sections if s["id"] == "evidence"), [])
    want = {str(x) for x in (selected_evidence_ids or [])}
    selected = [
        it for it in ev_items
        if not want or str(it.get("bookmark_id")) in want
    ]
    ctx: Dict[str, Any] = {
        "action": aid,
        "prompt": NB_AI_ACTION_PROMPTS.get(aid, ""),
        "header": collaborate_header(
            inv, broken=broken, selected_count=len(selected),
        ),
        "investigation": {
            "title": str(inv.get("title") or ""),
            "status": str(inv.get("status") or ""),
            "trace_identity": dict(inv.get("trace_identity") or {}),
            "sections": sections,
        },
        "selected_evidence": selected,
    }
    if aid == "update_from_findings":
        ctx["findings"] = [
            {
                "rule_id": str(f.get("rule_id") or f.get("id") or ""),
                "title": str(f.get("title") or ""),
                "severity": str(f.get("severity") or ""),
                "task": str(f.get("task") or ""),
            }
            for f in (findings or []) if isinstance(f, dict)
        ][:20]
    return ctx


# ---------------------------------------------------------------------------
# §10 — require proposal review before AI changes the Notebook
# ---------------------------------------------------------------------------
PROPOSAL_SCHEMA = "btf-viewer-nb-proposal/1"
PROPOSAL_OPS = ("add", "update", "link", "change_status", "remove")
# Op outcomes.
OP_OK = "ok"
OP_CONFIRM = "needs_confirmation"
OP_REJECTED = "rejected"



def strip_model_secrets(meta: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """Keep model / provider identity only — never keys, tokens or prompts."""
    m = meta if isinstance(meta, dict) else {}
    out: Dict[str, Any] = {}
    for k in ("model", "provider", "context_mode"):
        if m.get(k):
            out[k] = str(m[k])
    return out


def _bookmark_index(inv: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    return {str(b.get("id")): b for b in (inv.get("bookmarks") or [])}


def _annotate_op(
    inv: Dict[str, Any],
    op: Dict[str, Any],
    *,
    trace_hash: str,
    allow_other_trace: bool,
) -> Dict[str, Any]:
    kind = str(op.get("op") or "").strip().lower()
    out = dict(op)
    out["op"] = kind
    if kind not in PROPOSAL_OPS:
        out["status"], out["reason"] = OP_REJECTED, f"unknown op {kind!r}"
        return out
    bidx = _bookmark_index(inv)

    # An op that points at another trace needs an explicit Compare action.
    op_trace = str(op.get("trace_id") or "")
    if op_trace and op_trace != trace_hash and not allow_other_trace:
        out["status"] = OP_REJECTED
        out["reason"] = "references another trace without an explicit Compare action"
        return out

    if kind == "add":
        role = str(op.get("role") or op.get("type") or "").strip().lower()
        if role not in EVIDENCE_BOOKMARK_TYPES:
            out["status"], out["reason"] = OP_REJECTED, "add needs an evidence role"
            return out
        card = normalize_evidence_card(
            {
                "source": op.get("source"), "kind": op.get("kind"),
                "author": op.get("author") or EV_AUTHOR_AI,
                "task": op.get("task"), "unit": op.get("unit"),
                "value": op.get("value"), "scope": op.get("scope"),
            },
            refs=op.get("refs"),
        )
        out["card"] = card
        if str(op.get("kind") or "").lower() == EV_KIND_MEASURED and (
            not card or card.get("kind") != EV_KIND_MEASURED
        ):
            out["reason"] = "downgraded from Measured — AI prose is not measured"
        if role in ("supporting", "contradicting") and not (
            op.get("evidence_ids") or op.get("rationale")
        ):
            out.setdefault("reason", "no supporting evidence id cited")
        out["status"] = OP_OK
        return out

    if kind == "update":
        target = bidx.get(str(op.get("bookmark_id") or ""))
        if target is None:
            out["status"], out["reason"] = OP_REJECTED, "unknown bookmark_id"
            return out
        card = target.get("evidence") if isinstance(target.get("evidence"), dict) else {}
        _allowed, rejected = guard_evidence_changes(card, op.get("changes") or {})
        if rejected:
            out["status"] = OP_REJECTED
            out["reason"] = "measured data not changed: " + ", ".join(sorted(rejected))
            return out
        if target.get("type") == BM_CONCLUSION or "conclusion" in (op.get("changes") or {}):
            out["status"], out["reason"] = OP_CONFIRM, "replaces a conclusion"
            return out
        out["status"] = OP_OK
        return out

    if kind == "link":
        a, b = str(op.get("from") or ""), str(op.get("to") or "")
        if a not in bidx or b not in bidx or a == b:
            out["status"], out["reason"] = OP_REJECTED, "link needs two existing bookmarks"
            return out
        rel = str(op.get("relation") or "relates").strip().lower()
        if rel not in LINK_RELATIONS:
            out["status"], out["reason"] = OP_REJECTED, f"unknown relation {rel!r}"
            return out
        out["relation"] = rel
        out["status"] = OP_OK
        return out

    if kind == "change_status":
        s = str(op.get("status") or "").strip().lower()
        if s not in NOTEBOOK_STATUSES:
            out["status"], out["reason"] = OP_REJECTED, f"unknown status {s!r}"
            return out
        out["status_value"] = s
        if s == NB_STATUS_CLOSED:
            out["status"], out["reason"] = OP_CONFIRM, "closes the investigation"
            return out
        out["status"] = OP_OK
        return out

    # remove
    target = bidx.get(str(op.get("bookmark_id") or ""))
    if target is None:
        out["status"], out["reason"] = OP_REJECTED, "unknown bookmark_id"
        return out
    out["status"] = OP_CONFIRM
    out["reason"] = (
        "removes evidence" if target.get("type") in EVIDENCE_BOOKMARK_TYPES
        else "removes a bookmark"
    )
    return out


def validate_proposal(
    inv: Optional[Dict[str, Any]],
    proposal: Optional[Dict[str, Any]],
    *,
    findings: Optional[Sequence[Dict[str, Any]]] = None,  # noqa: ARG001 - reserved
    allow_other_trace: bool = False,
) -> Dict[str, Any]:
    """Validate every proposed op against references and protected fields.

    Returns ``{schema, ok, operations:[…annotated…], model}``; ``ok`` is True
    when at least one op is applicable (``ok`` or ``needs_confirmation``).
    """
    inv = load_investigation(inv)
    trace_hash = str((inv.get("trace_identity") or {}).get("hash") or "")
    raw = proposal if isinstance(proposal, dict) else {}
    ops = raw.get("operations") if isinstance(raw.get("operations"), list) else []
    annotated = [
        _annotate_op(
            inv, op if isinstance(op, dict) else {},
            trace_hash=trace_hash, allow_other_trace=bool(allow_other_trace),
        )
        for op in ops
    ]
    for i, op in enumerate(annotated):
        op["index"] = i
    applicable = any(o["status"] in (OP_OK, OP_CONFIRM) for o in annotated)
    return {
        "schema": PROPOSAL_SCHEMA,
        "ok": bool(applicable),
        "operations": annotated,
        "model": strip_model_secrets(raw.get("model")),
    }


def proposal_diff(
    inv: Optional[Dict[str, Any]],
    validated: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
    """Compact diff grouped by Notebook section for the review UI."""
    v = validated if isinstance(validated, dict) else {}
    by_section: Dict[str, List[Dict[str, Any]]] = {
        "hypotheses": [], "evidence": [], "conclusion": [], "status": [],
        "links": [],
    }
    needs_confirmation: List[Dict[str, Any]] = []
    rejected: List[Dict[str, Any]] = []
    for op in v.get("operations") or []:
        st = op.get("status")
        if st == OP_REJECTED:
            rejected.append(op)
            continue
        if st == OP_CONFIRM:
            needs_confirmation.append(op)
        kind = op.get("op")
        if kind == "add":
            role = str(op.get("role") or op.get("type") or "")
            by_section["hypotheses" if role == BM_HYPOTHESIS else "evidence"].append(op)
        elif kind == "update":
            by_section["conclusion" if "conclusion" in (op.get("changes") or {})
                       else "evidence"].append(op)
        elif kind == "change_status":
            by_section["status"].append(op)
        elif kind == "link":
            by_section["links"].append(op)
        elif kind == "remove":
            by_section["evidence"].append(op)
    return {
        "by_section": by_section,
        "needs_confirmation": needs_confirmation,
        "rejected": rejected,
    }


def apply_proposal(
    inv: Optional[Dict[str, Any]],
    validated: Optional[Dict[str, Any]],
    *,
    accept_indices: Optional[Sequence[int]] = None,
    accept_all: bool = False,
    confirmed_indices: Optional[Sequence[int]] = None,
    now: str = "",
) -> Tuple[Dict[str, Any], List[int], List[int]]:
    """Commit the accepted ops as one transaction. Returns ``(inv, applied,
    skipped)`` (op indices). The caller wraps the result in one
    ``push_notebook_state`` so undo reverts the whole proposal in one step.

    Nothing is applied without explicit acceptance — a ``needs_confirmation`` op
    is applied only when its index is in ``confirmed_indices`` *and* accepted.
    """
    v = validated if isinstance(validated, dict) else {}
    ops = v.get("operations") or []
    model = strip_model_secrets(v.get("model"))
    want = None if accept_all else {int(i) for i in (accept_indices or [])}
    confirmed = {int(i) for i in (confirmed_indices or [])}
    cur = load_investigation(inv)
    applied: List[int] = []
    skipped: List[int] = []
    for op in ops:
        i = int(op.get("index", -1))
        st = op.get("status")
        take = st == OP_OK or (st == OP_CONFIRM and i in confirmed)
        if want is not None:
            take = take and i in want
        if not take:
            skipped.append(i)
            continue
        cur = _apply_one(cur, op, model=model, now=now)
        applied.append(i)
    if applied:
        events = list(cur.get("proposal_events") or [])
        events.append({
            "schema": PROPOSAL_SCHEMA,
            "at": str(now or ""),
            "accepted": applied,
            "rejected": [
                int(o.get("index", -1)) for o in ops if o.get("status") == OP_REJECTED
            ],
            "model": model,
        })
        cur["proposal_events"] = events
    return cur, applied, skipped


def _apply_one(
    inv: Dict[str, Any], op: Dict[str, Any], *, model: Dict[str, Any], now: str,
) -> Dict[str, Any]:
    kind = op.get("op")
    if kind == "add":
        card = op.get("card") or {}
        out = add_evidence(
            inv,
            title=str(op.get("title") or "AI evidence"),
            note=str(op.get("note") or op.get("rationale") or ""),
            role=str(op.get("role") or op.get("type") or "supporting"),
            source=str(card.get("source") or "AI suggestion"),
            kind=str(card.get("kind") or ""),
            author=EV_AUTHOR_AI,
            refs=op.get("refs"),
            task=str(card.get("task") or ""),
            value=card.get("value"),
            unit=str(card.get("unit") or ""),
            scope=card.get("scope"),
            hypothesis_id=str(op.get("hypothesis_id") or ""),
            created_at=str(now or ""),
        )
        return _tag_ai_prov(
            out,
            {
                "model": model.get("model", ""),
                "provider": model.get("provider", ""),
                "source_evidence_ids": [
                    str(x) for x in (op.get("evidence_ids") or [])
                ],
            },
            now,
        )
    if kind == "update":
        if "conclusion" in (op.get("changes") or {}):
            return set_conclusion(inv, str(op["changes"]["conclusion"] or ""))
        note = (op.get("changes") or {}).get("note")
        if note is not None:
            return update_evidence_explanation(
                inv, str(op.get("bookmark_id") or ""), str(note), updated_at=now,
            )
        return inv
    if kind == "link":
        return link_bookmarks(
            inv, str(op.get("from") or ""), str(op.get("to") or ""),
            str(op.get("relation") or "relates"),
        )
    if kind == "change_status":
        return set_status(inv, str(op.get("status_value") or op.get("status") or ""),
                          updated_at=now)
    if kind == "remove":
        return remove_bookmark(inv, str(op.get("bookmark_id") or ""))
    return inv


def _tag_ai_prov(inv: Dict[str, Any], prov: Dict[str, Any], now: str) -> Dict[str, Any]:
    """Stamp AI provenance on the just-added last bookmark's evidence card."""
    bms = inv.get("bookmarks") or []
    if bms and isinstance(bms[-1].get("evidence"), dict):
        bms[-1]["evidence"]["ai_provenance"] = {
            "model": str(prov.get("model") or ""),
            "provider": str(prov.get("provider") or ""),
            "source_evidence_ids": list(prov.get("source_evidence_ids") or []),
        }
        bms[-1]["evidence"]["updated_at"] = str(now or "")
    return inv
