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

import json
import re
from typing import Any, Dict, List, Optional, Sequence, Tuple

from .investigation_notebook import (
    BM_CONCLUSION,
    BM_HYPOTHESIS,
    EVIDENCE_BOOKMARK_TYPES,
    EVIDENCE_KIND_LABELS,
    EV_AUTHOR_AI,
    EV_KIND_MEASURED,
    LINK_RELATIONS,
    NB_STATUS_CLOSED,
    NOTEBOOK_STATUSES,
    add_bookmark,
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

# The one reply contract every collaborate action (except refine_question) must
# follow, so the Notebook can render the answer as a select-and-add proposal
# card instead of a wall of prose. Lockstep with investigationAi.js's
# NB_PROPOSAL_REPLY_FORMAT.
NB_PROPOSAL_REPLY_FORMAT = "\n".join((
    "Reply with ONE ```json fenced block and NOTHING before or after it — no",
    'commentary, no "next steps", no links, and do NOT put it inside a markdown',
    "list or numbered step. The block is exactly:",
    '{"schema":"btf-viewer-nb-proposal/1","summary":"<1-2 plain sentences>",',
    ' "notes":["<short point>", ...],"operations":[<op>, ...]}',
    "Each op is exactly one of:",
    ' {"op":"add","role":"observation|supporting|contradicting|hypothesis","title":"...","note":"<your words>","evidence_ids":["E1"]}',
    ' {"op":"update","bookmark_id":"E1","changes":{"note":"..."}}  or  {"op":"update","changes":{"conclusion":"..."}}',
    ' {"op":"link","from":"E1","to":"H1","relation":"supports|contradicts|verifies|relates"}',
    ' {"op":"change_status","status":"open|closed"}',
    'Use "operations":[] when you are only reviewing. Cite only evidence ids shown in the',
    'context; never use kind "measured" or a "supported" status; every hypothesis stays "open".',
))

_NB_AI_TASKS: Tuple[Tuple[str, str, str], ...] = (
    ("review_investigation", "Review investigation",
     "Review this investigation for unsupported claims, contradictions and weak or "
     'missing evidence; put each finding in "notes". Where the evidence is too thin '
     'to support a conclusion, ALSO return "add" operations naming the specific next '
     "evidence to collect — which BTFViewer Statistics section or tool would produce "
     "it and what it would show — so the investigation can reach at least "
     'Derived-strength evidence. Otherwise "operations":[].'),
    ("gather_evidence", "Gather evidence",
     "Collect evidence for the open question by CALLING BTFViewer tools. Call tools "
     "as many times as needed — one round per gap — until every claim you would make "
     'is backed by measured tool output. Then return "add" operations (role '
     '"supporting" or "observation") whose "note" cites the exact tool and the '
     'numbers it returned; list anything you still could not substantiate in "notes".'),
    ("suggest_next_check", "Suggest next check",
     "Recommend exactly one evidence-producing next action (a BTFViewer tool call or a "
     'Statistics/Timeline step). Put it and the reason in "summary"; "operations":[].'),
    ("draft_hypotheses", "Draft hypotheses",
     'Propose up to three hypotheses for the open question as "add" operations with '
     'role "hypothesis", each citing in evidence_ids the id(s) it rests on.'),
    ("draft_conclusion", "Draft conclusion",
     'Draft a conclusion from the accepted Notebook evidence as one "update" operation '
     "with changes.conclusion. State the limitations and verification state in it."),
    ("update_from_findings", "Update from Findings",
     'Propose evidence cards from the listed Analysis Findings as "add" operations '
     '(role "supporting" or "observation"); each "note" must reference the finding.'),
    ("compare_trace", "Compare with another trace",
     "Compare with the other open trace (Baseline A vs Candidate B, current Compare "
     'Scope) and propose "add" operations for the notable differences.'),
)

NB_AI_ACTIONS: Tuple[Tuple[str, str, str], ...] = tuple(
    (aid, label, f"{task}\n\n{NB_PROPOSAL_REPLY_FORMAT}")
    for aid, label, task in _NB_AI_TASKS
) + (
    ("refine_question", "Help refine question",
     "Suggest one clearer, more specific rewording of this investigation "
     "question. Return only the improved question text on its own line, "
     'prefixed with "Suggested question: ". No JSON, no other operations.'),
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


_SUGGESTED_QUESTION_RE = re.compile(r"Suggested question:\s*(.+)", re.IGNORECASE)


def parse_question_suggestion(reply_text: Optional[str]) -> str:
    """Extract the AI's suggested question from a ``refine_question`` reply.

    Bypasses the proposal machinery entirely — a single scalar field (the
    question text) doesn't need the operations/proposal review pipeline.
    Returns ``''`` on any non-matching text; never invents from unstructured
    prose. Lockstep with ``web/src/utils/investigationAi.js``'s
    ``parseQuestionSuggestion``.
    """
    m = _SUGGESTED_QUESTION_RE.search(str(reply_text or ""))
    if not m:
        return ""
    return m.group(1).strip().strip("\"'")


_RB_HEADING_HASH_RE = re.compile(r"^#{1,6}\s+")
_RB_HEADING_BOLD_RE = re.compile(r"^\*\*[^*]+\*\*:?\s*$")
_RB_BULLET_RE = re.compile(r"^([-*•]|\d+[.)])\s+")


def _rb_clean(s: str) -> str:
    s = re.sub(r"\*\*(.+?)\*\*", r"\1", str(s))
    s = re.sub(r"`([^`]+)`", r"\1", s)
    s = re.sub(r"^#{1,6}\s*", "", s)
    return s.strip()


def parse_reply_blocks(reply_text: Optional[str]) -> List[Dict[str, Any]]:
    """Turn a prose AI reply into ``[{title, items:[]}]`` for the Notebook's
    right panel. Markdown headings (``#``..``######``, or a lone ``**Bold:**``
    line) start a section; bullet / numbered / plain lines become items; inline
    ``**`` / `` ` `` and a leading ``#`` are stripped. Falls back to one
    untitled section. Lockstep with ``investigationAi.js``'s
    ``parseReplyBlocks`` — used only for a reply that is not a structured
    proposal.
    """
    raw = str(reply_text or "")
    if not raw:
        return []
    blocks: List[Dict[str, Any]] = []
    cur: Optional[Dict[str, Any]] = None
    for raw_line in raw.split("\n"):
        line = raw_line.strip()
        if not line:
            continue
        if _RB_HEADING_HASH_RE.match(line) or _RB_HEADING_BOLD_RE.match(line):
            cur = {"title": re.sub(r":$", "", _rb_clean(line)), "items": []}
            blocks.append(cur)
            continue
        if cur is None:
            cur = {"title": "", "items": []}
            blocks.append(cur)
        cur["items"].append(_rb_clean(_RB_BULLET_RE.sub("", line)))
    return [b for b in blocks if b["title"] or b["items"]]


_NB_FENCE_RE = re.compile(r"```(?:json)?\s*([\s\S]*?)```", re.IGNORECASE)
_NB_LIST_MARKER_RE = re.compile(r"^\s*(?:[*+\-]|\d+[.)])\s+")


def _strip_list_markers(s: str) -> str:
    return "\n".join(
        _NB_LIST_MARKER_RE.sub("", ln) for ln in str(s).split("\n")
    ).strip()


def extract_notebook_proposal(text: Optional[str]) -> Optional[Dict[str, Any]]:
    """Pull a ``btf-viewer-nb-proposal/…`` object out of a model reply even when
    the model wrapped it in a ```json fence, a markdown list, or surrounded it
    with prose / "next step" links. Returns the object (``operations`` defaulted
    to ``[]``) or ``None``. Lockstep with ``investigationAi.js``'s
    ``extractNotebookProposal``.
    """
    raw = str(text or "")
    candidates: List[str] = list(_NB_FENCE_RE.findall(raw))
    candidates.append(raw)
    s_idx = raw.find("btf-viewer-nb-proposal/")
    if s_idx >= 0:
        open_i = raw.rfind("{", 0, s_idx)
        if open_i >= 0:
            depth = 0
            for i in range(open_i, len(raw)):
                if raw[i] == "{":
                    depth += 1
                elif raw[i] == "}":
                    depth -= 1
                    if depth == 0:
                        candidates.append(raw[open_i:i + 1])
                        break
    for c in candidates:
        try:
            obj = json.loads(_strip_list_markers(c))
        except (ValueError, TypeError):
            continue
        if (
            isinstance(obj, dict)
            and str(obj.get("schema") or "").startswith("btf-viewer-nb-proposal/")
            and (isinstance(obj.get("operations"), list)
                 or obj.get("summary") or isinstance(obj.get("notes"), list))
        ):
            if not isinstance(obj.get("operations"), list):
                obj["operations"] = []
            return obj
    return None


# Explicit reply budget for a Notebook collaboration turn. The proposal JSON
# (summary + notes + operations, often CJK) does not fit the Compact 500-token
# cap, and leaving it unset lets a local server apply its own small default --
# both truncate the JSON mid-string. Sent as max_tokens for every NB collab
# request regardless of context mode. Lockstep with investigationAi.js.
NB_PROPOSAL_REPLY_TOKENS = 4096

NB_PROPOSAL_TRUNCATED_HINT = (
    "The AI's reply was cut off before the Notebook proposal finished. The "
    "model likely hit its output limit or stopped early -- try a larger / "
    "stronger model, shrink the request (narrower Scope, fewer findings, clear "
    "a long chat), and for a local server make sure its context window is large "
    "(Ollama: `OLLAMA_CONTEXT_LENGTH` / `num_ctx` >= 8192, and restart it). "
    "Then run this action again."
)


def looks_like_truncated_proposal(text: Optional[str]) -> bool:
    """Heuristic: the reply was emitting a ``btf-viewer-nb-proposal`` but was cut
    off before the JSON closed (a local model running out of context mid-answer).
    True only when a proposal marker is present, extraction failed, and the
    braces from the marker onward stay unbalanced. Lockstep with
    ``investigationAi.js``'s ``looksLikeTruncatedProposal``.
    """
    raw = str(text or "")
    if not raw.strip() or "btf-viewer-nb-proposal" not in raw:
        return False
    if extract_notebook_proposal(raw) is not None:
        return False
    s_idx = raw.find("btf-viewer-nb-proposal")
    open_i = raw.rfind("{", 0, s_idx)
    if open_i < 0:
        return False
    depth = 0
    for i in range(open_i, len(raw)):
        if raw[i] == "{":
            depth += 1
        elif raw[i] == "}":
            depth -= 1
            if depth == 0:
                return False
    return depth > 0


_NB_FENCE_ANY_RE = re.compile(r"```(?:json)?\s*[\s\S]*?```", re.IGNORECASE)
_NB_LINK_LINE_RE = re.compile(r"\]\((?:btfnext|btfstats):", re.IGNORECASE)
_NB_SCHEMA_LINE_RE = re.compile(r'"schema"\s*:\s*"btf-viewer-nb-proposal')


def summarize_notebook_proposal_for_chat(text: Optional[str]) -> str:
    """Rewrite an assistant reply that carries a ``btf-viewer-nb-proposal/…``
    object so the AI panel (and the Notebook) show a readable summary instead
    of a raw JSON code block + "next step" link soup. No-op when the text has
    no proposal. Lockstep with investigationAi.js's
    ``summarizeNotebookProposalForChat``.
    """
    raw = str(text or "")
    obj = extract_notebook_proposal(raw)
    if not obj:
        return raw

    rest_lines: List[str] = []
    for ln in _NB_FENCE_ANY_RE.sub("", raw).split("\n"):
        s = _NB_LIST_MARKER_RE.sub("", ln.strip())
        if not s or s in ("`", "```"):
            continue
        if _NB_SCHEMA_LINE_RE.search(s) or _NB_LINK_LINE_RE.search(s):
            continue
        rest_lines.append(s)
    rest = "\n".join(rest_lines).strip()

    ops = obj.get("operations") if isinstance(obj.get("operations"), list) else []
    n_ops = len(ops)
    out: List[str] = ["**AI proposal for the Investigation Notebook**"]
    summary = str(obj.get("summary") or "").strip()
    if summary:
        out += ["", summary]
    notes = [str(n or "").strip() for n in (obj.get("notes") or [])]
    notes = [n for n in notes if n]
    if notes:
        out.append("")
        out += [f"- {n}" for n in notes]
    # P0.3 — the proposal review opens the Notebook itself; no "open the
    # Notebook" instruction, and no Review action for zero operations.
    out += ["", (
        f"_{n_ops} change{'' if n_ops == 1 else 's'} proposed._"
        if n_ops else
        "_No Notebook changes proposed._"
    )]
    if rest:
        out += ["", rest]
    return "\n".join(out)


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


def collaborate_digest(ctx: Optional[Dict[str, Any]]) -> str:
    """Human-readable Markdown digest of a :func:`collaborate_context` payload —
    what the AI actually receives, formatted for a person to skim (no JSON).
    Used as the message context sent to the model and in the AI panel's
    "what's sent" disclosure. Lockstep with ``collaborateDigest`` (web).
    """
    c = ctx if isinstance(ctx, dict) else {}
    inv = c.get("investigation") or {}
    by_id: Dict[str, List[Dict[str, Any]]] = {}
    for s in inv.get("sections") or []:
        by_id[s.get("id")] = s.get("items") or []
    out: List[str] = []
    first = (by_id.get("question") or [{}])[0] if by_id.get("question") else {}
    out.append(f"**Question** — {first.get('text') or '_(untitled)_'}")
    scope = [i.get("text") for i in (by_id.get("scope") or []) if i.get("text")]
    if scope:
        out.append("**Scope** — " + " · ".join(scope))

    hyp = by_id.get("hypotheses") or []
    if hyp:
        out += ["", f"**Hypotheses ({len(hyp)})**"]
        for h in hyp:
            st = f"  _({h.get('status')})_" if h.get("status") else ""
            out.append(f"- {h.get('text')}{st}")

    ev = c.get("selected_evidence") or by_id.get("evidence") or []
    if ev:
        out += ["", f"**Evidence ({len(ev)})**"]
        for e in ev:
            kind = e.get("kind")
            label = (EVIDENCE_KIND_LABELS.get(kind)
                     if kind and kind != "note" else None) or EVIDENCE_KIND_LABELS[""]
            note = str(e.get("note") or "").split("\n")[0].strip()
            stale = "  ⚠ stale reference" if e.get("stale") else ""
            out.append(f"- _[{label}]_ {e.get('text')}"
                       + (f" — {note}" if note else "") + stale)

    checks = [i.get("text") for i in (by_id.get("open_checks") or []) if i.get("text")]
    if checks:
        out += ["", f"**Open checks ({len(checks)})**"]
        out += [f"- {t}" for t in checks]

    verdict = [i.get("text") for i in (by_id.get("conclusion") or [])
               if i.get("kind") == "verdict" and i.get("text")]
    out += ["", "**Conclusion** — " + (" ".join(verdict) if verdict else "_none yet_")]
    return "\n".join(out)


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
        if role not in (*EVIDENCE_BOOKMARK_TYPES, BM_HYPOTHESIS):
            out["status"], out["reason"] = (
                OP_REJECTED, "add needs an evidence or hypothesis role")
            return out
        # Normalise so proposal_diff routing and apply() agree regardless of
        # how the model cased the role.
        out["role"] = role
        # A hypothesis has no evidence card — it is an interpretation the user
        # still has to verify. Accept it, but flag one missing its evidence
        # citation; it can never be applied as anything but 'open'.
        if role == BM_HYPOTHESIS:
            out["status"] = OP_OK
            if not (op.get("evidence_ids") or str(op.get("rationale") or "").strip()):
                out["reason"] = "hypothesis cites no evidence id"
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

    Returns ``{schema, ok, summary, notes, operations:[…annotated…], model}``;
    ``ok`` is True when at least one op is applicable (``ok`` or
    ``needs_confirmation``). ``summary`` / ``notes`` carry a review-only reply.
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
    raw_notes = raw.get("notes") if isinstance(raw.get("notes"), list) else []
    notes = [str(n if n is not None else "").strip() for n in raw_notes]
    notes = [n for n in notes if n]
    return {
        "schema": PROPOSAL_SCHEMA,
        "ok": bool(applicable),
        "summary": str(raw.get("summary") or "").strip(),
        "notes": notes,
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
        role = str(op.get("role") or op.get("type") or "supporting").strip().lower()
        if role == BM_HYPOTHESIS:
            # Add the hypothesis bookmark, then wire each cited evidence id that
            # resolves to a real bookmark as a 'supports' link (the demo's
            # "Add hypothesis" outcome). Missing / self ids are skipped.
            out = add_bookmark(
                inv,
                type=BM_HYPOTHESIS,
                title=str(op.get("title") or "AI hypothesis"),
                note=str(op.get("note") or op.get("rationale") or ""),
                refs=op.get("refs"),
            )
            bms = out.get("bookmarks") or []
            new_id = str(bms[-1].get("id")) if bms else ""
            known = {str(b.get("id")) for b in bms}
            for ev_id in (str(x) for x in (op.get("evidence_ids") or [])):
                if ev_id and ev_id != new_id and ev_id in known:
                    out = link_bookmarks(out, ev_id, new_id, "supports")
            return out
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
