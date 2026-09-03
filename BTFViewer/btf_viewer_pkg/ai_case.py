"""Investigation Case lifecycle: hypotheses, evidence graph, quality, validation.

Host-side (deterministic) layer on top of Analysis Findings / tool results.
Keep behaviour in sync with ``web/src/utils/aiCase.js``.
"""
from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

HYPOTHESIS_STATUSES: Tuple[str, ...] = (
    "supported", "possible", "rejected", "need_evidence",
)
EVIDENCE_QUALITY_BANDS: Tuple[str, ...] = (
    "strong", "medium-high", "medium", "weak", "insufficient",
)
INVESTIGATION_MODES: Tuple[str, ...] = (
    "quick", "diagnose", "compare", "optimize", "report",
)
INVESTIGATION_SCOPE_OPTIONS: Tuple[str, ...] = (
    "execution", "blocking", "migrations", "priority inheritance",
    "nearby events", "findings", "tick",
)
EXPLAIN_LEVELS: Tuple[str, ...] = ("quick", "technical", "deep")
PRIVACY_LEVELS: Tuple[str, ...] = ("local", "cloud_safe", "sensitive")
CASE_SCHEMA = "btf-investigation-case"
CASE_VERSION = 1

_JUMP_RE = re.compile(r"jump:([0-9]+(?:\.[0-9]+)?)", re.IGNORECASE)
_TASK_NAME_RE = re.compile(
    r"\b([A-Za-z][A-Za-z0-9_.-]*\[\d+\])"
)
_METRIC_WORDS = (
    "migrations", "blocking", "execution", "wcet", "latency",
    "priority", "inheritance", "mutex", "tick", "deadline",
    "load", "balance", "preemption", "contention", "dwell",
)
_KNOWN_METRICS = frozenset(_METRIC_WORDS + (
    "priority_inheritance", "sync", "findings", "cpu", "response",
))
_MERMAID_STRIP_RE = re.compile(r'["[\]{}()|]')

_TOOL_REASONS: Dict[str, str] = {
    "detect_anomalies": "Rank Findings as Critical / Warning / Info before drilling in",
    "investigate": "Build hypotheses and an evidence chain for the focus finding",
    "correlate_events": "Check whether blocking, migrations, and sync overlap the spike",
    "query_raw_metric": "Pull a scoped per-task series instead of guessing numbers",
    "find_critical_path": "Walk preempt / block / mutex around the evidence time",
    "detect_priority_inversion": "Test L/M/H inversion as an alternative to contention",
    "search_timeline": "Locate STI / tag / task timestamps like Find",
    "compare_performance": "Measure A vs B deltas instead of narrating them",
    "what_if": "Score a concrete pin / priority / contention experiment",
    "optimize_experiment": "Rank automatic mitigation candidates",
    "explain_finding": "Produce a levelled explanation of the selected finding",
    "interpret_query": "Turn the user's question into an explicit investigation scope",
    "validate_experiment": "Compare expected experiment deltas with a new capture",
    "manage_hypotheses": "Mark a hypothesis supported, rejected, or needing evidence",
    "plan_investigation": "Plan the cheapest tool sequence and rank hypotheses first",
    "suggest_scope": "Recommend task and time window before gathering evidence",
    "detect_contradictions": "Challenge the leading hypothesis against metrics",
    "assess_evidence_sufficiency": "Stop when coverage is enough",
    "cluster_findings": "Group related findings into one incident",
    "generate_fingerprint": "Compact scheduling/sync/timing signature",
    "find_similar_investigations": "Match this fingerprint to recorded outcomes",
    "regression_localize": "Pin A vs B inflation to a task and region",
    "build_causal_chain": "Causal vs correlated vs temporal edges",
    "generate_experiment_plan": "Rank concrete firmware / what-if experiments",
    "record_experiment_outcome": "Feed measured results back into recommendations",
    "score_investigation": "Evidence efficiency, cost, stop, and falsification scores",
    "analyze_temporal_causality": "Order findings into a happens-before chain",
    "build_task_dependency_graph": "Task/resource graph from BTF sync, preemption, and migration",
    "decompose_response_time": "Split delay into blocking, preemption, and execution",
    "rank_root_causes": "Rank likely causes across findings and hypotheses",
    "verify_claim": "Check a causal claim against findings and scope",
    "challenge_conclusion": "List alternatives and missing evidence",
    "investigation_memory": "Store or recall similar past investigations",
    "cluster_incidents": "Group findings by time proximity",
    "close_investigation": "Record a conclusion and close the case",
    "analyze_distribution": "p50/p90/p99/p99.9, stddev, CV, and 3-sigma outlier rate",
    "analyze_periodicity": "Period/jitter (RMS, peak-to-peak) and kind: drift vs release vs WCET vs scheduler",
    "summarize_investigation_context": "Compact findings, hypotheses, and tools run",
}


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(round(float(value)))
    except (TypeError, ValueError):
        return default


def _mermaid_safe_label(text: Any, limit: int = 96) -> str:
    cleaned = _MERMAID_STRIP_RE.sub("", str(text or "").replace("\n", " "))
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return (cleaned or "Node")[:limit]


def mermaid_label_with_time(text: Any, time: Any = None, limit: int = 96) -> str:
    """Node text plus ``jump:TIME`` so diagram clicks pan the timeline."""
    lab = str(text or "").strip() or "Node"
    tok = ""
    try:
        tn = float(time)
        tok = str(int(tn)) if tn.is_integer() else str(tn)
    except (TypeError, ValueError):
        tok = ""
    if tok and f"jump:{tok}" not in lab:
        lab = f"{lab} jump:{tok}"
    return _mermaid_safe_label(lab, limit)


GUIDED_STAGES: Tuple[str, ...] = (
    "triage", "scope", "investigate", "verify", "experiment", "compare",
)
GUIDED_STAGE_LABELS: Dict[str, str] = {
    "idle": "Start",
    "triage": "Triage",
    "scope": "Scope",
    "investigate": "Investigate",
    "verify": "Verify",
    "experiment": "Experiment",
    "compare": "Compare",
}

AI_CONTEXT_MODE_COMPACT = "compact"
AI_CONTEXT_MODE_BALANCED = "balanced"
AI_CONTEXT_MODE_FULL = "full"
AI_CONTEXT_MODES: Tuple[str, ...] = (
    AI_CONTEXT_MODE_COMPACT, AI_CONTEXT_MODE_BALANCED, AI_CONTEXT_MODE_FULL,
)
DEFAULT_AI_CONTEXT_MODE = AI_CONTEXT_MODE_BALANCED
AI_CONTEXT_MODE_LABELS: Dict[str, str] = {
    AI_CONTEXT_MODE_COMPACT: "Compact",
    AI_CONTEXT_MODE_BALANCED: "Balanced",
    AI_CONTEXT_MODE_FULL: "Full Evidence",
}
AI_CONTEXT_MODE_SETTINGS_TOOLTIP = (
    "How much Findings, tools, and chat history are sent to the model. "
    "Confidence comes from evidence, not from the mode."
)
AI_CONTEXT_MODE_SETTINGS_LINES: Dict[str, str] = {
    AI_CONTEXT_MODE_COMPACT: (
        "Compact — Fast triage; up to 3 findings and minimal tools."
    ),
    AI_CONTEXT_MODE_BALANCED: (
        "Balanced (default) — Default investigation with evidence and one "
        "alternative."
    ),
    AI_CONTEXT_MODE_FULL: (
        "Full Evidence — Deep verification with relevant evidence and "
        "investigation history."
    ),
}

AI_CONTEXT_PROMPTS: Dict[str, str] = {
    AI_CONTEXT_MODE_COMPACT: "MODE: COMPACT\n- Fast triage; target 250\u2013500 answer tokens.\n- Use the scope summary and up to three actionable findings.\n- Use at most two evidence calls unless the user requests more work.\n- Do not run planning, graphs, simulation, optimization, memory, clustering, or\n  reports unless requested.\n- Preserve viewer state. Do not create diagrams unless requested.\n- If evidence is insufficient, return Inconclusive and name what is missing.\n- Still include concrete Evidence (names, values with units, jump:TIME when\n  known). Do not answer with a one-line summary only.\n- Output: Assessment; Evidence; Confidence/quality; Next check.",
    AI_CONTEXT_MODE_BALANCED: "MODE: BALANCED\n- Default mode; target 600\u20131200 answer tokens.\n- Use relevant scoped findings and tables; fetch exact evidence when needed.\n- Test the leading explanation and one credible alternative.\n- Prefer at most four evidence calls for ad-hoc questions. Follow Preferred tools\n  on Start Investigation / template workflows even when that needs more calls.\n  Exceed the preference whenever another result could change the verdict.\n  Verify before a High-confidence causal conclusion.\n- Change viewer state only for an explicit action or a workflow that promises to\n  focus evidence.\n- Use one small diagram only when it materially improves understanding.\n- Write a full engineering answer: Verdict; Evidence with jump:TIME / values;\n  Interpretation; Alternative/falsification; Confidence/quality/coverage;\n  Next action. Do not over-compress into a stub.",
    AI_CONTEXT_MODE_FULL: "MODE: FULL EVIDENCE\n- Use all relevant scoped evidence and compact investigation history.\n- Rank hypotheses for broad questions; skip planning for an explicit finding,\n  task, and window.\n- Build causal or dependency chains only as far as evidence supports.\n- Examine contradictions and credible alternatives. Assess sufficiency before\n  opening another branch; stop when more tools will not change the verdict.\n- Verify and challenge before a High-confidence root-cause conclusion.\n- Distinguish observed, derived, heuristic, and simulated results.\n- Preserve unrelated viewer marks. Use diagrams only for supported relationships.\n- State each material fact once. Return Inconclusive when evidence remains\n  incomplete or contradictory.\n- Target a thorough write-up (about 1000\u20132000 answer tokens) when evidence\n  supports it. Output: Scope; Verdict; Evidence chain with times/values;\n  Contradictions/alternatives; Root cause or leading explanation;\n  Confidence/quality/coverage; Requested mitigation; Next verification;\n  Viewer changes.",
}

AI_LANGUAGE_PROMPT_TEMPLATE = (
    "Always write your entire reply in {language}.\n"
    "Write the complete user-facing reply in {language}, including section "
    "headings and bullet labels.\n"
    "Preserve task names, core names, UI labels, tool names, metric "
    "identifiers, jump:TIME, range:LO/HI, code, and file formats. Do not "
    "translate trace identifiers."
)
AI_LANGUAGE_TRADITIONAL_CHINESE_NOTE = (
    "Use natural Traditional Chinese and terminology customary in Taiwan.\n"
    "Write section headings in Traditional Chinese too "
    "(for example 結論、證據、置信度), not English.\n"
    "Do not switch to English or Simplified Chinese for the prose answer."
)
AI_LANGUAGE_SIMPLIFIED_CHINESE_NOTE = (
    "Use natural Simplified Chinese.\n"
    "Write section headings in Simplified Chinese too "
    "(for example 结论、证据、置信度), not English.\n"
    "Do not switch to English or Traditional Chinese for the prose answer."
)
AI_LANGUAGE_KOREAN_NOTE = (
    "Use natural Korean Hangul (한국어).\n"
    "Write section headings in Korean too, not English.\n"
    "Do not switch to English or Chinese for the prose answer."
)
AI_LANGUAGE_REMINDER_MARKER = "REPLY LANGUAGE (mandatory)"
AI_TOOL_ROUND_LIMIT_PROMPT = (
    "You have reached the tool-call limit for this turn. "
    "Do not call any more tools — summarize your findings and "
    "give your final answer now in plain text."
)
AI_EMPTY_REPLY_NUDGE = (
    "Your previous reply was empty (no text and no tool call). "
    "Answer now with a short analysis, or call a tool."
)

# Stage-only tool names for Compact; Balanced adds neighbours + extras.
AI_CONTEXT_STAGE_TOOLS: Dict[str, Tuple[str, ...]] = {
    "triage": ("detect_anomalies", "cluster_findings", "suggest_scope"),
    "scope": ("set_cursors", "zoom_to_range", "highlight_task", "open_statistics_section"),
    "investigate": ("investigate", "correlate_events", "find_critical_path"),
    "verify": ("verify_claim", "detect_contradictions", "challenge_conclusion"),
    "experiment": ("what_if", "optimize_experiment", "recommend_experiments"),
    "compare": ("compare_performance", "validate_experiment"),
    "report": ("generate_report", "export_report"),
}
AI_CONTEXT_ALWAYS_TOOLS: Tuple[str, ...] = (
    "search_timeline", "query_raw_metric", "summarize_investigation_context",
)
AI_CONTEXT_BALANCED_EXTRA_TOOLS: Tuple[str, ...] = (
    "detect_anomalies", "investigate", "set_cursors", "zoom_to_range",
    "highlight_task", "challenge_conclusion",
)
_CONTEXT_TOOL_ROW_KEYS: Tuple[str, ...] = (
    "rows", "episodes", "slices", "events", "gaps", "hits", "times",
    "experiments", "anomalies", "candidates", "samples", "values",
)
_FINDING_ITEM_RE = re.compile(r"(?m)^(\d+)\. \[([A-Z]+)\]")
_SEV_CONTEXT_RANK = {"error": 0, "critical": 0, "warning": 1, "info": 2}


def normalize_ai_context_mode(value: Any) -> str:
    """Settings → AI context mode (default Balanced)."""
    raw = str(value or "").strip().lower().replace("-", " ").replace("_", " ")
    if raw in ("compact", "reduced", "reduce", "low"):
        return AI_CONTEXT_MODE_COMPACT
    if raw in ("balanced", "balance", "medium", "default balanced"):
        return AI_CONTEXT_MODE_BALANCED
    if raw in ("full", "full evidence", "fullevidence", "complete", "max"):
        return AI_CONTEXT_MODE_FULL
    return DEFAULT_AI_CONTEXT_MODE


def ai_context_mode_label(mode: Any) -> str:
    return AI_CONTEXT_MODE_LABELS.get(
        normalize_ai_context_mode(mode), AI_CONTEXT_MODE_LABELS[DEFAULT_AI_CONTEXT_MODE])


def ai_context_mode_settings_overview() -> str:
    """Multi-line Settings → AI help describing all three context modes."""
    return "\n".join(AI_CONTEXT_MODE_SETTINGS_LINES[m] for m in AI_CONTEXT_MODES)


def ai_context_mode_settings_help(mode: Any = None) -> str:
    """One-line Settings help for the selected context mode."""
    key = normalize_ai_context_mode(mode)
    return AI_CONTEXT_MODE_SETTINGS_LINES.get(
        key, AI_CONTEXT_MODE_SETTINGS_LINES[DEFAULT_AI_CONTEXT_MODE])


def ai_context_limits(mode: Any = None) -> Dict[str, Any]:
    """Token-budget knobs for Compact / Balanced / Full evidence."""
    key = normalize_ai_context_mode(mode)
    if key == AI_CONTEXT_MODE_COMPACT:
        return {
            "findings": 5,
            "tool_rows": 10,
            "history_user_turns": 2,
            "max_tokens": 500,
            "what_if": 3,
            "diagrams": "asked",
        }
    if key == AI_CONTEXT_MODE_FULL:
        return {
            "findings": None,
            "tool_rows": 40,
            "history_user_turns": 20,
            "max_tokens": None,
            "what_if": 12,
            "diagrams": "useful",
        }
    return {
        "findings": 12,
        "tool_rows": 20,
        "history_user_turns": 6,
        "max_tokens": None,
        "what_if": 5,
        "diagrams": "useful",
    }


def context_mode_system_addendum(mode: Any = None) -> str:
    """Context-mode system prompt block (AI_CONTEXT_PROMPTS)."""
    key = normalize_ai_context_mode(mode)
    return AI_CONTEXT_PROMPTS.get(key, AI_CONTEXT_PROMPTS[DEFAULT_AI_CONTEXT_MODE])


def ai_language_prompt(language: Any = None) -> str:
    """Reply-language instruction for every Settings language."""
    lang = str(language or "English").strip() or "English"
    text = AI_LANGUAGE_PROMPT_TEMPLATE.replace("{language}", lang).rstrip()
    low = lang.lower()
    if "traditional chinese" in low or "繁體" in lang or "繁体" in lang:
        text = text + "\n" + AI_LANGUAGE_TRADITIONAL_CHINESE_NOTE.rstrip()
    elif "simplified chinese" in low or "简体" in lang or "簡體" in lang:
        text = text + "\n" + AI_LANGUAGE_SIMPLIFIED_CHINESE_NOTE.rstrip()
    elif "한국" in lang or "korean" in low:
        text = text + "\n" + AI_LANGUAGE_KOREAN_NOTE.rstrip()
    elif low not in ("english",):
        text = (
            text
            + f"\nDo not answer in English unless the user explicitly asks for English. "
            + f"All headings, bullets, and explanations must be in {lang}."
        )
    return text


def ai_language_reminder(language: Any = None) -> str:
    """Short sticky reminder for non-English turns (user + follow-up nudges)."""
    lang = str(language or "English").strip() or "English"
    low = lang.lower()
    if low == "english":
        return ""
    marker = AI_LANGUAGE_REMINDER_MARKER
    keep = (
        "Keep task/core names, jump:TIME, range:LO/HI, tool names, and UI "
        "labels unchanged."
    )
    if "traditional chinese" in low or "繁體" in lang or "繁体" in lang:
        return (
            f"{marker}: Traditional Chinese (繁體中文) / 台灣用語. "
            "Write all user-facing prose and section headings in 繁體中文. "
            "Do not answer in English or Simplified Chinese. "
            f"{keep}"
        )
    if "simplified chinese" in low or "简体" in lang or "簡體" in lang:
        return (
            f"{marker}: Simplified Chinese (简体中文). "
            "Write all user-facing prose and section headings in 简体中文. "
            "Do not answer in English or Traditional Chinese. "
            f"{keep}"
        )
    if "한국" in lang or "korean" in low:
        return (
            f"{marker}: Korean (한국어). "
            "Write all user-facing prose and section headings in 한국어. "
            "Do not answer in English or Chinese. "
            f"{keep}"
        )
    return (
        f"{marker}: {lang}. "
        f"Write all user-facing prose and section headings in {lang}. "
        "Do not answer in English unless the user explicitly asks for English. "
        f"{keep}"
    )


def with_ai_language_reminder(text: Any = "", language: Any = None) -> str:
    """Append ``ai_language_reminder`` when the selected language is not English."""
    body = str(text or "").strip()
    rem = ai_language_reminder(language)
    if not rem:
        return body
    if not body:
        return rem
    if rem in body:
        return body
    return f"{body}\n\n{rem}"


def _stage_tool_names(stage: Any) -> Tuple[str, ...]:
    sid = str(stage or "").strip().lower()
    if sid in ("", "idle", "start"):
        sid = "triage"
    return AI_CONTEXT_STAGE_TOOLS.get(sid, AI_CONTEXT_STAGE_TOOLS["triage"])


def tool_names_for_context_mode(
    mode: Any = None,
    stage: Any = "",
) -> Optional[List[str]]:
    """Tool names to send, or None to send the full catalog."""
    key = normalize_ai_context_mode(mode)
    if key == AI_CONTEXT_MODE_FULL:
        return None
    names: List[str] = []
    seen = set()

    def _add(seq: Sequence[str]) -> None:
        for name in seq:
            n = str(name or "").strip()
            if n and n not in seen:
                seen.add(n)
                names.append(n)

    sid = str(stage or "").strip().lower()
    if sid in ("", "idle", "start"):
        sid = "triage"
    _add(_stage_tool_names(sid))
    _add(AI_CONTEXT_ALWAYS_TOOLS)
    if key == AI_CONTEXT_MODE_BALANCED:
        if sid in GUIDED_STAGES:
            idx = list(GUIDED_STAGES).index(sid)
            if idx > 0:
                _add(_stage_tool_names(GUIDED_STAGES[idx - 1]))
            if idx + 1 < len(GUIDED_STAGES):
                _add(_stage_tool_names(GUIDED_STAGES[idx + 1]))
        _add(AI_CONTEXT_BALANCED_EXTRA_TOOLS)
        # Report/export only for report stage (or when a neighbour is report).
        if sid == "report":
            _add(AI_CONTEXT_STAGE_TOOLS["report"])
        elif sid in GUIDED_STAGES:
            idx = list(GUIDED_STAGES).index(sid)
            for j in (idx - 1, idx + 1):
                if 0 <= j < len(GUIDED_STAGES) and GUIDED_STAGES[j] == "report":
                    _add(AI_CONTEXT_STAGE_TOOLS["report"])
                    break
    return names


def filter_tools_for_context_mode(
    tools: Optional[Sequence[Dict[str, Any]]],
    mode: Any = None,
    stage: Any = "",
) -> List[Dict[str, Any]]:
    """Subset of OpenAI tool schemas for the selected context mode."""
    catalog = [t for t in (tools or []) if isinstance(t, dict)]
    names = tool_names_for_context_mode(mode, stage)
    if names is None:
        return list(catalog)
    want = set(names)
    out: List[Dict[str, Any]] = []
    for tool in catalog:
        fn = tool.get("function") if isinstance(tool.get("function"), dict) else {}
        name = str(fn.get("name") or "").strip()
        if name in want:
            out.append(tool)
    return out


def _finding_evidence_jump_tokens(finding: Optional[dict], *, limit: int = 4) -> List[str]:
    """Collect jump:TIME tokens from a finding's evidence list."""
    out: List[str] = []
    if not isinstance(finding, dict):
        return out
    for ev in finding.get("evidence") or []:
        if not isinstance(ev, dict) or ev.get("time") is None:
            continue
        token = str(ev.get("time")).strip()
        if not token:
            continue
        label = str(ev.get("label") or "event").strip() or "event"
        out.append(f"{label} jump:{token}")
        if len(out) >= max(1, int(limit)):
            break
    return out


def investigation_context_summary(payload: Optional[dict] = None) -> str:
    """Short investigation recap used instead of older chat turns."""
    if not isinstance(payload, dict) or not payload:
        return ""
    case = payload.get("investigation_case")
    if not isinstance(case, dict):
        case = {}
    finding = payload.get("finding")
    if not isinstance(finding, dict):
        finding = {}
    parts: List[str] = []
    title = str(
        case.get("goal") or finding.get("title") or finding.get("id") or ""
    ).strip()
    if title:
        parts.append(f"Focus: {title}")
    jumps = _finding_evidence_jump_tokens(finding)
    if not jumps:
        for ev in payload.get("evidence") or []:
            if not isinstance(ev, dict) or ev.get("time") is None:
                continue
            token = str(ev.get("time")).strip()
            if not token:
                continue
            label = str(ev.get("label") or "event").strip() or "event"
            jumps.append(f"{label} jump:{token}")
            if len(jumps) >= 4:
                break
    if jumps:
        parts.append("Evidence: " + "; ".join(jumps))
    chain = str(payload.get("evidence_chain") or "").strip()
    if chain:
        parts.append("Chain: " + chain[:180])
    quality = payload.get("evidence_quality")
    if isinstance(quality, dict):
        band = str(quality.get("band") or "").strip()
        if band:
            parts.append(f"Evidence quality: {band}")
    hyps = case.get("hypotheses") or payload.get("hypotheses") or []
    for hyp in hyps:
        if not isinstance(hyp, dict):
            continue
        text = str(hyp.get("hypothesis") or hyp.get("id") or "").strip()
        if not text:
            continue
        status = str(hyp.get("status") or "").strip()
        parts.append(f"- {status + ': ' if status else ''}{text}")
        if len(parts) >= 10:
            break
    tools = case.get("tools_executed") or payload.get("tools_executed") or []
    labels = [str(t).strip() for t in tools if str(t).strip()]
    if labels:
        parts.append("Tools: " + ", ".join(labels[:12]))
    return "\n".join(parts).strip()


def _finding_blocks(text: str) -> Tuple[str, List[Dict[str, str]]]:
    blob = str(text or "")
    matches = list(_FINDING_ITEM_RE.finditer(blob))
    if not matches:
        return blob.rstrip(), []
    header = blob[: matches[0].start()].rstrip()
    items: List[Dict[str, str]] = []
    for i, match in enumerate(matches):
        end = matches[i + 1].start() if i + 1 < len(matches) else len(blob)
        items.append({
            "sev": match.group(2).lower(),
            "block": blob[match.start():end].rstrip(),
        })
    return header, items



def focus_titles_from_summary(summary: Any = "") -> List[str]:
    """Titles from ``Focus: …`` lines in an investigation summary (for dedupe)."""
    out: List[str] = []
    for line in str(summary or "").splitlines():
        raw = line.strip()
        if raw.lower().startswith("focus:"):
            title = raw.split(":", 1)[1].strip()
            if title:
                out.append(title)
    return out


def _text_has_timed_evidence(text: Any) -> bool:
    """True when prose already carries a jump:TIME citation."""
    return bool(re.search(r"\bjump:\s*\S+", str(text or ""), flags=re.IGNORECASE))


def _finding_dict_has_timed_evidence(finding: Any) -> bool:
    if not isinstance(finding, dict):
        return False
    if _text_has_timed_evidence(finding.get("text")):
        return True
    if _finding_evidence_jump_tokens(finding, limit=1):
        return True
    return False


def compact_findings_text(
    text: Any,
    mode: Any = None,
    findings: Optional[Sequence[dict]] = None,
    *,
    exclude_titles: Optional[Sequence[str]] = None,
) -> str:
    """Keep the most important Findings for the selected context mode.

    *exclude_titles*: drop title-only duplicates already named in an
    investigation summary (``Focus: …``). Never drop a finding that still
    carries jump:TIME evidence — Focus alone is not a substitute.
    """
    limits = ai_context_limits(mode)
    cap = limits.get("findings")
    raw = str(text or "").rstrip()
    exclude = {
        str(x or "").strip().lower()
        for x in (exclude_titles or ())
        if str(x or "").strip()
    }
    if cap is None or not raw:
        return raw
    header, items = _finding_blocks(raw)
    if items:
        if exclude:
            filtered = []
            for it in items:
                block = it["block"]
                head = block.splitlines()[0] if block else ""
                # "1. [WARNING] id=x Title" or "1. [WARNING] Title"
                title = head
                m = re.match(r"^\d+\. \[[A-Z]+\](?: id=\S+)?\s*(.*)$", head)
                if m:
                    title = m.group(1).strip()
                fid_m = re.search(r"\bid=(\S+)", head)
                fid = fid_m.group(1) if fid_m else ""
                title_hit = title.lower() in exclude or (
                    fid.lower() in exclude if fid else False
                )
                # Keep timed evidence even when Focus names the same title.
                if title_hit and not _text_has_timed_evidence(block):
                    continue
                filtered.append(it)
            items = filtered or items
        ranked = sorted(
            enumerate(items),
            key=lambda row: (_SEV_CONTEXT_RANK.get(row[1]["sev"], 3), row[0]),
        )
        kept = [row[1]["block"] for row in ranked[: int(cap)]]
        omitted = max(0, len(items) - len(kept))
        lines = [header] if header else []
        if lines:
            lines.append("")
        lines.extend(kept)
        if omitted:
            lines.append("")
            lines.append(
                f"{omitted} more finding(s) omitted "
                f"({ai_context_mode_label(mode)}). Ask for Full evidence or a "
                "specific finding id if needed."
            )
        return "\n".join(lines).rstrip() + "\n"
    if findings:
        ranked: List[Tuple[Any, ...]] = []
        for i, finding in enumerate(findings):
            if not isinstance(finding, dict):
                continue
            title = str(finding.get("title") or "").strip()
            fid = str(finding.get("id") or "").strip()
            title_hit = exclude and (
                title.lower() in exclude or (fid.lower() in exclude if fid else False)
            )
            if title_hit and not _finding_dict_has_timed_evidence(finding):
                continue
            sev = str(finding.get("severity") or "info").lower()
            ranked.append((_SEV_CONTEXT_RANK.get(sev, 3), i, finding))
        ranked.sort(key=lambda row: row[:2])
        kept_f = [row[2] for row in ranked[: int(cap)]]
        omitted = max(0, len(ranked) - len(kept_f))
        lines = ["Analysis Findings", ""]
        for i, finding in enumerate(kept_f, 1):
            sev = str(finding.get("severity") or "info").upper()
            fid = str(finding.get("id") or "").strip()
            id_bit = f" id={fid}" if fid else ""
            lines.append(f"{i}. [{sev}]{id_bit} {finding.get('title') or 'Finding'}")
            lines.append(f"   {finding.get('text') or ''}")
            for ev in (finding.get("evidence") or []):
                if isinstance(ev, dict) and ev.get("time") is not None:
                    lines.append(
                        f"   evidence: {ev.get('label') or 'event'} jump:{ev.get('time')}"
                    )
                elif ev:
                    lines.append(f"   evidence: {ev}")
            lines.append("")
        if omitted:
            lines.append(
                f"{omitted} more finding(s) omitted "
                f"({ai_context_mode_label(mode)})."
            )
        return "\n".join(lines).rstrip() + "\n"
    if len(raw) > 8000 and normalize_ai_context_mode(mode) == AI_CONTEXT_MODE_COMPACT:
        return raw[:8000].rstrip() + "\n… (truncated for Compact context)\n"
    if len(raw) > 20000 and normalize_ai_context_mode(mode) == AI_CONTEXT_MODE_BALANCED:
        return raw[:20000].rstrip() + "\n… (truncated for Balanced context)\n"
    return raw if raw.endswith("\n") else raw + "\n"


def _truncate_tool_lists(obj: Any, row_cap: int, what_if_cap: int) -> Any:
    if isinstance(obj, list):
        if len(obj) > row_cap:
            return obj[:row_cap]
        return [_truncate_tool_lists(v, row_cap, what_if_cap) for v in obj]
    if not isinstance(obj, dict):
        return obj
    out: Dict[str, Any] = {}
    for key, value in obj.items():
        if key in ("experiments", "candidates") and isinstance(value, list):
            cap = min(row_cap, what_if_cap)
            if len(value) > cap:
                out[key] = [_truncate_tool_lists(v, row_cap, what_if_cap) for v in value[:cap]]
                out.setdefault("truncated", True)
                out["omitted"] = max(int(out.get("omitted") or 0), len(value) - cap)
            else:
                out[key] = [_truncate_tool_lists(v, row_cap, what_if_cap) for v in value]
        elif key in _CONTEXT_TOOL_ROW_KEYS and isinstance(value, list):
            if len(value) > row_cap:
                out[key] = [_truncate_tool_lists(v, row_cap, what_if_cap) for v in value[:row_cap]]
                out.setdefault("truncated", True)
                out["omitted"] = max(int(out.get("omitted") or 0), len(value) - row_cap)
            else:
                out[key] = [_truncate_tool_lists(v, row_cap, what_if_cap) for v in value]
        else:
            out[key] = _truncate_tool_lists(value, row_cap, what_if_cap)
    return out


def compact_tool_result_payload(
    result: Any,
    mode: Any = None,
    *,
    exclude_titles: Optional[Sequence[str]] = None,
) -> Any:
    """Shrink list-heavy tool payloads before they go back to the model.

    *exclude_titles*: drop finding-shaped rows already named in Findings /
    investigation Focus lines so the same issue is not resent in tool history.
    """
    limits = ai_context_limits(mode)
    row_cap = int(limits.get("tool_rows") or 40)
    what_if_cap = int(limits.get("what_if") or 12)
    payload = result
    parsed_json = False
    if isinstance(result, str):
        text = result.strip()
        if text.startswith("{") or text.startswith("["):
            try:
                payload = json.loads(text)
                parsed_json = True
            except ValueError:
                payload = result
    if not isinstance(payload, (dict, list)):
        return result
    exclude = {
        str(x or "").strip().lower()
        for x in (exclude_titles or ())
        if str(x or "").strip()
    }
    if exclude:
        payload = _strip_excluded_finding_titles(payload, exclude)
    compacted = _truncate_tool_lists(payload, row_cap, what_if_cap)
    if isinstance(compacted, dict) and compacted.get("omitted"):
        msg = str(compacted.get("message") or "").rstrip()
        extra = (
            f"{compacted['omitted']} more row(s) omitted "
            f"({ai_context_mode_label(mode)})."
        )
        compacted["message"] = f"{msg} {extra}".strip() if msg else extra
    if parsed_json:
        return json.dumps(compacted, default=str)
    return compacted


def _strip_excluded_finding_titles(payload: Any, exclude: set) -> Any:
    """Drop title-only finding duplicates already named in *exclude*.

    Never drop the primary ``finding`` object or any finding that still
    carries jump:TIME evidence — Start Investigation depends on those
    times surviving into later tool rounds.
    """
    if isinstance(payload, list):
        out = []
        for item in payload:
            if isinstance(item, dict):
                title = str(item.get("title") or "").strip().lower()
                fid = str(item.get("id") or "").strip().lower()
                title_hit = (title in exclude) or (fid in exclude if fid else False)
                if title_hit and not _finding_dict_has_timed_evidence(item):
                    continue
                out.append(_strip_excluded_finding_titles(item, exclude))
            else:
                out.append(_strip_excluded_finding_titles(item, exclude))
        return out
    if isinstance(payload, dict):
        out = {}
        for key, val in payload.items():
            if key in (
                "findings", "anomalies", "ranked_anomalies", "related_findings",
            ) and isinstance(val, list):
                out[key] = _strip_excluded_finding_titles(val, exclude)
            elif key == "finding" and isinstance(val, dict):
                # Always keep the primary finding payload (timed evidence + text).
                out[key] = _strip_excluded_finding_titles(val, exclude)
            else:
                out[key] = _strip_excluded_finding_titles(val, exclude)
        return out
    return payload


def compact_chat_history(
    messages: Optional[Sequence[Dict[str, Any]]],
    mode: Any = None,
    investigation_summary: str = "",
) -> List[Dict[str, Any]]:
    """Keep system + last N user turns (and their tool follow-ups)."""
    limits = ai_context_limits(mode)
    keep_turns = max(1, int(limits.get("history_user_turns") or 2))
    msgs = [m for m in (messages or []) if isinstance(m, dict)]
    system: List[Dict[str, Any]] = []
    rest: List[Dict[str, Any]] = []
    for msg in msgs:
        if str(msg.get("role") or "") == "system" and not rest:
            system.append(dict(msg))
        else:
            rest.append(dict(msg))
    user_idxs = []
    for i, msg in enumerate(rest):
        if str(msg.get("role") or "") != "user":
            continue
        content = str(msg.get("content") or "").lower()
        if "tool-call limit" in content:
            continue
        if "reply language (mandatory)" in content:
            continue
        user_idxs.append(i)
    omitted = 0
    if len(user_idxs) > keep_turns:
        omitted = len(user_idxs) - keep_turns
        rest = rest[user_idxs[-keep_turns]:]
    extra: List[Dict[str, Any]] = []
    if omitted:
        summary = str(investigation_summary or "").strip()
        if summary:
            extra.append({
                "role": "user",
                "content": "### Investigation summary\n" + summary,
            })
        else:
            extra.append({
                "role": "user",
                "content": (
                    f"[{omitted} earlier turn(s) omitted for "
                    f"{ai_context_mode_label(mode)} context.]"
                ),
            })
        extra.append({
            "role": "assistant",
            "content": "Understood. Continue from the recent turns.",
        })
    compacted: List[Dict[str, Any]] = []
    exclude = focus_titles_from_summary(investigation_summary)
    for msg in rest:
        copied = dict(msg)
        if str(copied.get("role") or "") == "tool":
            copied["content"] = compact_tool_result_payload(
                copied.get("content"), mode, exclude_titles=exclude)
        compacted.append(copied)
    return system + extra + compacted


def format_context_usage_status(
    meter: Optional[dict] = None,
    mode: Any = None,
) -> str:
    """AI panel usage bar: ``Context: Compact · 1.3k tok · 2 tools · 1.5s``."""
    label = ai_context_mode_label(mode)
    m = meter if isinstance(meter, dict) else empty_cost_meter()
    try:
        tokens = int(m.get("total_tokens") or 0)
    except (TypeError, ValueError):
        tokens = 0
    try:
        tools = int(m.get("tool_calls") or 0)
    except (TypeError, ValueError):
        tools = 0
    try:
        time_s = float(m.get("model_time_s") or 0)
    except (TypeError, ValueError):
        time_s = 0.0
    if tokens <= 0 and tools <= 0 and time_s <= 0:
        return f"Context: {label}"
    time_part = f"{time_s:g}s" if time_s else "0s"
    return (
        f"Context: {label} · {_format_token_count(tokens)} tok · "
        f"{tools} tools · {time_part}"
    )


def _guide_tool_names(payload: Optional[dict], plan: Optional[dict]) -> List[str]:
    names: List[str] = []
    if isinstance(payload, dict):
        case = payload.get("investigation_case") or {}
        for t in (case.get("tools_executed") or payload.get("tools_executed") or []):
            names.append(str(t or "").strip())
        for t in (payload.get("suggested_tools") or []):
            if isinstance(t, dict):
                names.append(str(t.get("name") or "").strip())
            else:
                names.append(str(t or "").strip())
    if isinstance(plan, dict):
        for s in (plan.get("steps") or []):
            if isinstance(s, dict):
                names.append(str(s.get("id") or s.get("label") or "").strip())
            else:
                names.append(str(s or "").strip())
    return [n for n in names if n]


def investigation_guide_stage(
    payload: Optional[dict] = None,
    *,
    plan: Optional[dict] = None,
    has_cursors: bool = False,
    has_two_traces: bool = False,
) -> str:
    """Map an Investigation Case onto the beginner stepper stage."""
    tools = " ".join(_guide_tool_names(payload, plan)).lower()
    has_payload = isinstance(payload, dict) and bool(payload)
    has_plan = isinstance(plan, dict) and bool(plan.get("steps") or plan.get("goal"))
    if not has_payload and not has_plan:
        return "idle"
    # Report mode plans list generate_report / export_report. Map those onto the
    # report tool stage so Balanced/Compact include export_report (GUIDED_STAGES
    # has no "report" chip, but stage selection still drives the tool catalog).
    if "generate_report" in tools or "export_report" in tools:
        return "report"
    quality = ""
    if has_payload:
        q = payload.get("evidence_quality") or {}
        if isinstance(q, dict):
            quality = str(q.get("band") or "").lower()
    verified = any(k in tools for k in (
        "verify_claim", "detect_contradictions", "assess_evidence_sufficiency",
        "challenge_conclusion",
    )) or quality in ("strong", "medium-high")
    if has_two_traces and (
        "validate_experiment" in tools or "compare_performance" in tools
        or "analyze_traces" in tools
    ):
        return "compare"
    if "what_if" in tools or "optimize_experiment" in tools:
        return "experiment" if verified else "verify"
    if verified:
        return "verify"
    if any(k in tools for k in (
        "investigate", "correlate_events", "find_critical_path",
        "rank_root_causes",
    )) or (has_payload and (payload.get("evidence") or payload.get("root_cause_chain"))):
        return "investigate"
    if has_cursors:
        return "scope"
    return "triage"


GUIDE_STAGE_NEEDLES: Dict[str, Tuple[str, ...]] = {
    "triage": ("finding", "triage", "analysis"),
    "scope": ("cursor", "scope", "c1"),
    "investigate": ("evidence", "correlate", "critical path", "root cause"),
    "verify": ("verify", "contradict", "alternative", "sufficiency"),
    "experiment": ("what-if", "what_if", "optimize", "estimate"),
    "compare": ("compare", "validate_experiment", "recapture"),
}
ESTIMATE_BANNER = (
    "Simulation / estimate — not measured RTOS behavior."
)
VERIFY_HINT = (
    "Verify alternatives and contradictions before treating What-if as measured."
)


def guide_stage_needles(stage: str) -> Tuple[str, ...]:
    return GUIDE_STAGE_NEEDLES.get(str(stage or ""), ())


def investigation_issue_card(payload: Optional[dict] = None) -> Dict[str, str]:
    """Compact CURRENT ISSUE fields for the AI panel card."""
    data = payload if isinstance(payload, dict) else {}
    finding = data.get("finding") if isinstance(data.get("finding"), dict) else {}
    quality = data.get("evidence_quality") if isinstance(data.get("evidence_quality"), dict) else {}
    interpreted = data.get("interpreted") if isinstance(data.get("interpreted"), dict) else {}
    title = str(
        finding.get("title") or data.get("conclusion") or data.get("subtitle") or ""
    ).strip()
    task = ""
    for key in ("task", "task_name", "primary_task"):
        task = str(finding.get(key) or interpreted.get(key) or "").strip()
        if task:
            break
    scope = str(interpreted.get("scope") or data.get("scope") or "").strip()
    return {
        "title": title or "Investigation",
        "severity": str(finding.get("severity") or "").strip(),
        "task": task,
        "band": str(quality.get("band") or "").replace("-", " ").title(),
        "scope": scope,
        "status": str(data.get("conclusion") or "").strip()[:120],
    }


def format_investigation_issue_card(card: Optional[dict] = None) -> str:
    """Desktop/Web lockstep text for the AI panel Current issue strip."""
    data = card if isinstance(card, dict) else {}
    title = str(data.get("title") or "").strip()
    task = str(data.get("task") or "").strip()
    band = str(data.get("band") or "").strip()
    scope = str(data.get("scope") or "").strip()
    if title in ("", "Investigation") and not task and not band:
        return ""
    bits = [title or "Investigation"]
    if task:
        bits.append(task)
    if band:
        bits.append(f"Evidence {band}")
    if scope:
        bits.append(scope)
    return "CURRENT ISSUE\n" + " · ".join(bits)


AI_SESSION_MAX_MESSAGES = 40
AI_SESSION_MAX_CHARS = 80000


def dump_investigation_session(
    *,
    payload: Optional[dict] = None,
    plan: Optional[dict] = None,
    messages: Optional[Sequence[Any]] = None,
) -> str:
    """JSON for session restore (evidence + plan + recent chat)."""
    msgs: List[Dict[str, str]] = []
    total = 0
    for raw in list(messages or [])[-AI_SESSION_MAX_MESSAGES:]:
        if isinstance(raw, dict):
            role = str(raw.get("role") or "")
            text = str(raw.get("content") or raw.get("text") or "")
        elif isinstance(raw, (list, tuple)) and len(raw) >= 2:
            role = str(raw[0] or "")
            text = str(raw[1] or "")
        else:
            continue
        if role not in ("user", "assistant", "evidence"):
            continue
        if total + len(text) > AI_SESSION_MAX_CHARS:
            break
        total += len(text)
        msgs.append({"role": role, "content": text[:8000]})
    blob = {
        "v": 1,
        "payload": payload if isinstance(payload, dict) else None,
        "plan": plan if isinstance(plan, dict) else None,
        "messages": msgs,
    }
    return json.dumps(blob, ensure_ascii=False, separators=(",", ":"))


def parse_investigation_session(raw: Any) -> Dict[str, Any]:
    if isinstance(raw, dict):
        data = raw
    else:
        text = str(raw or "").strip()
        if not text:
            return {"payload": None, "plan": None, "messages": []}
        try:
            data = json.loads(text)
        except (TypeError, ValueError, json.JSONDecodeError):
            return {"payload": None, "plan": None, "messages": []}
    if not isinstance(data, dict):
        return {"payload": None, "plan": None, "messages": []}
    msgs = []
    for m in (data.get("messages") or [])[:AI_SESSION_MAX_MESSAGES]:
        if not isinstance(m, dict):
            continue
        role = str(m.get("role") or "")
        if role not in ("user", "assistant", "evidence"):
            continue
        msgs.append({"role": role, "content": str(m.get("content") or "")[:8000]})
    payload = data.get("payload") if isinstance(data.get("payload"), dict) else None
    plan = data.get("plan") if isinstance(data.get("plan"), dict) else None
    return {"payload": payload, "plan": plan, "messages": msgs}


def investigation_session_has_chat(messages: Optional[Sequence[Any]] = None) -> bool:
    """True when a session blob has a user or assistant turn (not evidence-only)."""
    for raw in messages or []:
        if isinstance(raw, dict):
            role = str(raw.get("role") or "")
            text = str(raw.get("content") or raw.get("text") or "")
        elif isinstance(raw, (list, tuple)) and len(raw) >= 2:
            role = str(raw[0] or "")
            text = str(raw[1] or "")
        else:
            continue
        if role in ("user", "assistant") and text.strip():
            return True
    return False


def empty_investigation_case(
    *,
    question: str = "",
    trace: str = "",
    cursor_lo: Optional[float] = None,
    cursor_hi: Optional[float] = None,
    tasks: Optional[Sequence[str]] = None,
    cores: Optional[Sequence[str]] = None,
) -> Dict[str, Any]:
    """Empty Investigation Case envelope."""
    return {
        "schema": CASE_SCHEMA,
        "version": CASE_VERSION,
        "question": str(question or "").strip(),
        "scope": {
            "trace": str(trace or "").strip(),
            "cursor_lo": cursor_lo,
            "cursor_hi": cursor_hi,
            "tasks": [str(t) for t in (tasks or []) if str(t).strip()],
            "cores": [str(c) for c in (cores or []) if str(c).strip()],
        },
        "suspected_findings": [],
        "hypotheses": [],
        "evidence": [],
        "tools_executed": [],
        "tool_reasons": [],
        "evidence_timeline": [],
        "evidence_graph": {},
        "evidence_quality": {},
        "evidence_coverage": {},
        "falsification": {},
        "confidence": "Medium",
        "confidence_history": [],
        "conclusion": "",
        "alternatives_rejected": [],
        "recommended_action": "",
        "validation": {},
        "mode": "diagnose",
    }


def add_finding_to_case(
    case: Optional[Dict[str, Any]],
    finding: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
    """Append *finding* to ``suspected_findings`` (dedupe by id). Lockstep JS."""
    out = dict(case) if isinstance(case, dict) else empty_investigation_case()
    if not isinstance(finding, dict):
        return out
    fid = str(finding.get("id") or "").strip()
    items = [
        dict(x) for x in (out.get("suspected_findings") or [])
        if isinstance(x, dict)
    ]
    if fid:
        items = [x for x in items if str(x.get("id") or "").strip() != fid]
    items.append(dict(finding))
    out["suspected_findings"] = items
    title = str(finding.get("title") or finding.get("observation") or fid).strip()
    if title and not str(out.get("goal") or "").strip():
        out["goal"] = title
    if title and not str(out.get("conclusion") or "").strip():
        out["conclusion"] = title
    if title and not str(out.get("question") or "").strip():
        out["question"] = title
    task = str(finding.get("task") or "").strip()
    if task:
        scope = dict(out.get("scope") or {})
        tasks = [str(t) for t in (scope.get("tasks") or []) if str(t).strip()]
        if task not in tasks:
            tasks.append(task)
        scope["tasks"] = tasks
        out["scope"] = scope
    return out


def _finding_blob(finding: Optional[dict]) -> str:
    if not isinstance(finding, dict):
        return ""
    return f"{finding.get('title') or ''} {finding.get('text') or ''}"


def enrich_hypotheses(
    hypotheses: Optional[Sequence[dict]],
    *,
    evidence: Optional[Sequence[dict]] = None,
    alternatives: Optional[Sequence[dict]] = None,
) -> List[Dict[str, Any]]:
    """Attach status / confidence / evidence_count to heuristic hypotheses."""
    ev = [e for e in (evidence or []) if isinstance(e, dict)]
    timed = sum(1 for e in ev if e.get("time") is not None)
    kinds = set()
    for e in ev:
        label = str(e.get("label") or e.get("kind") or "")
        kind = label.split(":", 1)[0].strip().lower() if ":" in label else label.lower()
        if kind:
            kinds.add(kind)
    alt_status = {
        str(a.get("hypothesis") or "").strip().lower(): str(a.get("status") or "").lower()
        for a in (alternatives or []) if isinstance(a, dict)
    }
    out: List[Dict[str, Any]] = []
    for i, raw in enumerate(hypotheses or []):
        if not isinstance(raw, dict):
            continue
        hyp = str(raw.get("hypothesis") or "").strip()
        if not hyp:
            continue
        why = str(raw.get("why") or "").strip()
        status = str(raw.get("status") or "").strip().lower()
        if status not in HYPOTHESIS_STATUSES:
            mapped = alt_status.get(hyp.lower(), "")
            if mapped == "rejected":
                status = "rejected"
            elif mapped == "confirmed" or (i == 0 and timed):
                status = "supported"
            elif i == 0:
                status = "possible"
            elif timed and any(k in hyp.lower() for k in kinds):
                status = "possible"
            else:
                status = "need_evidence"
        if status == "supported":
            conf = 70 + min(25, 8 * timed) - 4 * i
        elif status == "possible":
            conf = 40 + min(20, 5 * timed) - 6 * i
        elif status == "rejected":
            conf = max(5, 18 - 4 * i)
        else:
            conf = 22 - 4 * i
        out.append({
            "id": str(raw.get("id") or f"h{i + 1}"),
            "hypothesis": hyp,
            "why": why,
            "status": status,
            "confidence": max(0, min(100, int(conf))),
            "evidence_count": timed if status in ("supported", "possible") else 0,
        })
    return out


def set_hypothesis_status(
    hypotheses: Sequence[dict],
    hypothesis_id: str,
    status: str,
    *,
    reason: str = "",
) -> List[Dict[str, Any]]:
    """Return a copy with one hypothesis status updated."""
    want = str(hypothesis_id or "").strip().lower()
    st = str(status or "").strip().lower()
    if st not in HYPOTHESIS_STATUSES:
        st = "need_evidence"
    out: List[Dict[str, Any]] = []
    for i, h in enumerate(hypotheses or []):
        if not isinstance(h, dict):
            continue
        item = dict(h)
        hid = str(item.get("id") or f"h{i + 1}").lower()
        name = str(item.get("hypothesis") or "").strip().lower()
        if hid == want or name == want or str(i + 1) == want:
            item["status"] = st
            if reason:
                item["why"] = str(reason).strip()
            if st == "supported":
                item["confidence"] = max(_safe_int(item.get("confidence"), 70), 70)
            elif st == "rejected":
                item["confidence"] = min(_safe_int(item.get("confidence"), 18), 25)
        out.append(item)
    return out


def compare_hypotheses(hypotheses: Sequence[dict]) -> Dict[str, Any]:
    """Rank hypotheses by status then confidence."""
    items = [h for h in (hypotheses or []) if isinstance(h, dict)]
    rank = {"supported": 0, "possible": 1, "need_evidence": 2, "rejected": 3}
    ranked = sorted(
        items,
        key=lambda h: (
            rank.get(str(h.get("status") or ""), 9),
            -_safe_int(h.get("confidence")),
        ),
    )
    leader = ranked[0] if ranked else None
    return {
        "ok": True,
        "ranked": ranked,
        "leader": leader,
        "supported": [h for h in ranked if h.get("status") == "supported"],
        "rejected": [h for h in ranked if h.get("status") == "rejected"],
    }


def build_evidence_graph(
    finding: Optional[dict] = None,
    *,
    evidence: Optional[Sequence[dict]] = None,
    hypotheses: Optional[Sequence[dict]] = None,
    chain: Optional[Sequence[dict]] = None,
) -> Dict[str, Any]:
    """Provenance graph: finding → evidence / chain → hypotheses."""
    nodes: List[Dict[str, Any]] = []
    edges: List[Dict[str, Any]] = []
    fid = "F"
    title = ""
    if isinstance(finding, dict):
        title = str(finding.get("title") or finding.get("id") or "Finding")
        nodes.append({
            "id": fid, "kind": "finding", "label": title,
            "time": None,
        })
    ev_items = [e for e in (evidence or []) if isinstance(e, dict)]
    for i, ev in enumerate(ev_items[:12]):
        nid = f"E{i}"
        nodes.append({
            "id": nid,
            "kind": "evidence",
            "label": mermaid_label_with_time(
                ev.get("label") or ev.get("kind") or "evidence", ev.get("time")),
            "time": ev.get("time"),
        })
        if any(n["id"] == fid for n in nodes):
            edges.append({"from": fid, "to": nid, "rel": "observed"})
    for i, step in enumerate((chain or [])[:8]):
        if not isinstance(step, dict):
            continue
        nid = f"C{i}"
        nodes.append({
            "id": nid,
            "kind": str(step.get("kind") or "step"),
            "label": mermaid_label_with_time(
                step.get("label") or f"Step {i + 1}", step.get("time")),
            "time": step.get("time"),
        })
        prev = fid if i == 0 and any(n["id"] == fid for n in nodes) else f"C{i - 1}"
        if i == 0 and any(n["id"] == fid for n in nodes):
            edges.append({"from": fid, "to": nid, "rel": "chain"})
        elif i > 0:
            edges.append({"from": prev, "to": nid, "rel": "chain"})
    for j, h in enumerate((hypotheses or [])[:8]):
        if not isinstance(h, dict):
            continue
        nid = f"H{j}"
        status = str(h.get("status") or "possible")
        rel = "supports" if status == "supported" else (
            "contradicts" if status == "rejected" else "hypothesizes"
        )
        nodes.append({
            "id": nid,
            "kind": "hypothesis",
            "label": str(h.get("hypothesis") or f"Hypothesis {j + 1}"),
            "status": status,
            "time": None,
        })
        if any(n["id"] == fid for n in nodes):
            edges.append({"from": fid, "to": nid, "rel": rel})
    return {
        "nodes": nodes,
        "edges": edges,
        "mermaid": evidence_graph_mermaid(nodes, edges),
    }


def evidence_graph_mermaid(
    nodes: Optional[Sequence[dict]] = None,
    edges: Optional[Sequence[dict]] = None,
) -> str:
    items = [n for n in (nodes or []) if isinstance(n, dict) and n.get("id")]
    if not items:
        return ""
    lines = ["graph TD"]
    for n in items:
        nid = str(n.get("id"))
        label = _mermaid_safe_label(n.get("label") or nid)
        kind = str(n.get("kind") or "")
        if kind == "hypothesis":
            lines.append(f"{nid}({label})")
        elif kind == "evidence":
            lines.append(f"{nid}{{{{{label}}}}}")
        else:
            lines.append(f"{nid}[{label}]")
    for e in (edges or []):
        if not isinstance(e, dict):
            continue
        src, dst = str(e.get("from") or ""), str(e.get("to") or "")
        if not src or not dst:
            continue
        rel = str(e.get("rel") or "").strip()
        if rel and rel not in ("observed", "chain"):
            lines.append(f"{src} -- {rel} --> {dst}")
        else:
            lines.append(f"{src} --> {dst}")
    return "\n".join(lines)


def evidence_quality_band(score: Any) -> str:
    """Map a 0–100 heuristic score onto a qualitative band (not a probability)."""
    n = max(0, min(100, _safe_int(score)))
    if n >= 80:
        return "strong"
    if n >= 65:
        return "medium-high"
    if n >= 45:
        return "medium"
    if n >= 25:
        return "weak"
    return "insufficient"


def quality_bar(band: str, width: int = 10) -> str:
    filled_map = {
        "strong": width,
        "medium-high": max(1, int(round(width * 0.8))),
        "medium": max(1, int(round(width * 0.55))),
        "weak": max(1, int(round(width * 0.3))),
        "insufficient": 0,
    }
    filled = filled_map.get(str(band or ""), 0)
    label = {
        "strong": "Strong",
        "medium-high": "Medium-High",
        "medium": "Medium",
        "weak": "Weak",
        "insufficient": "Insufficient",
    }.get(str(band or ""), "Insufficient")
    return "█" * filled + "░" * (width - filled) + f" {label}"


def compute_evidence_quality(
    *,
    score: Any = 0,
    breakdown: Optional[Sequence[dict]] = None,
    evidence: Optional[Sequence[dict]] = None,
    alternatives: Optional[Sequence[dict]] = None,
    checks: Optional[Sequence[dict]] = None,
    evidence_chain: str = "",
) -> Dict[str, Any]:
    """Qualitative Evidence Quality (heuristic, not a statistical CI)."""
    ev = [e for e in (evidence or []) if isinstance(e, dict)]
    alts = [a for a in (alternatives or []) if isinstance(a, dict)]
    chks = [c for c in (checks or []) if isinstance(c, dict)]
    has_direct = any(e.get("time") is not None for e in ev)
    kinds = set()
    for e in ev:
        label = str(e.get("label") or "")
        if ":" in label:
            kind = label.split(":", 1)[0].strip().lower()
            if kind:
                kinds.add(kind)
    has_timeline = len(kinds) >= 2 or bool(str(evidence_chain or "").strip())
    has_metric = bool(chks)
    untested = [
        a for a in alts
        if str(a.get("status") or "").lower() in (
            "untested", "need_evidence", "needs_evidence", "",
        )
    ]
    alt_mark = "yes" if alts and not untested else ("partial" if alts else "no")
    band = evidence_quality_band(score)
    flags = {
        "direct_evidence": has_direct,
        "timeline_correlation": has_timeline,
        "metric_correlation": has_metric,
        "alternative_tested": alt_mark,
    }
    return {
        "band": band,
        "bar": quality_bar(band),
        "score": max(0, min(100, _safe_int(score))),
        "label": "Evidence Quality",
        "flags": flags,
        "breakdown": list(breakdown or []),
        "confidence_label": {
            "strong": "High",
            "medium-high": "Medium-High",
            "medium": "Medium",
            "weak": "Low",
            "insufficient": "Low",
        }.get(band, "Low"),
    }


def compute_evidence_coverage(
    *,
    claims: Optional[Sequence[dict]] = None,
    evidence: Optional[Sequence[dict]] = None,
    known_tasks: Optional[Sequence[str]] = None,
    known_metrics: Optional[Sequence[str]] = None,
) -> Dict[str, Any]:
    """Fraction of extracted claims that are grounded in evidence / known names."""
    claim_items = [c for c in (claims or []) if isinstance(c, dict)]
    ev = [e for e in (evidence or []) if isinstance(e, dict)]
    tasks = {str(t).strip().lower() for t in (known_tasks or []) if str(t).strip()}
    metrics = {
        str(m).strip().lower() for m in (known_metrics or _KNOWN_METRICS) if str(m).strip()
    }
    timed = {e.get("time") for e in ev if e.get("time") is not None}
    total = len(claim_items) or 0
    observed = 0
    timeline = 0
    metric_ok = 0
    unverified = 0
    for c in claim_items:
        kind = str(c.get("kind") or "")
        ok = bool(c.get("ok"))
        if kind in ("timestamp", "jump"):
            if ok or c.get("value") in timed:
                timeline += 1
                observed += 1
            else:
                unverified += 1
        elif kind == "task":
            name = str(c.get("value") or "").strip().lower()
            if ok or name in tasks:
                observed += 1
            else:
                unverified += 1
        elif kind == "metric":
            name = str(c.get("value") or "").strip().lower()
            if ok or name in metrics:
                metric_ok += 1
                observed += 1
            else:
                unverified += 1
        else:
            if ok:
                observed += 1
            else:
                unverified += 1
    denom = total or 1
    pct = int(round(100.0 * observed / denom)) if total else (100 if ev else 0)
    # Timed evidence on the panel is coverage. Validation claims extracted
    # from the final reply must not collapse the meter to 0%.
    if ev and (not claim_items or observed == 0):
        observed = min(len(ev), 7)
        total = max(len(ev), 7)
        timeline = sum(1 for e in ev if e.get("time") is not None)
        pct = int(round(100.0 * min(1.0, observed / float(max(total, 1)))))
    return {
        "percent": max(0, min(100, pct)),
        "bar": (
            "█" * max(0, min(10, int(round(10 * max(0, min(100, pct)) / 100.0))))
            + "░" * (10 - max(0, min(10, int(round(10 * max(0, min(100, pct)) / 100.0)))))
            + f" {max(0, min(100, pct))}%"
        ),
        "directly_observed": f"{observed}/{total or observed}",
        "timeline_verified": timeline,
        "metric_verified": metric_ok,
        "unverified_assumptions": unverified,
        "claims": total,
    }


def _quality_flag_mark(value: Any) -> str:
    if value is True or str(value).lower() in ("yes", "true", "1"):
        return "✓"
    if str(value).lower() in ("partial", "triangle", "maybe"):
        return "△"
    return "○"


def format_quality_flag_lines(
    quality: Optional[dict] = None,
    labels: Optional[Dict[str, str]] = None,
) -> List[str]:
    """Checklist under Evidence Quality (direct / timeline / metric / alternative)."""
    lab = labels if isinstance(labels, dict) else {}
    flags = (quality or {}).get("flags") if isinstance(quality, dict) else {}
    flags = flags if isinstance(flags, dict) else {}
    rows = (
        ("direct_evidence", "quality_direct", "Direct evidence"),
        ("timeline_correlation", "quality_timeline", "Timeline correlation"),
        ("metric_correlation", "quality_metric", "Metric correlation"),
        ("alternative_tested", "quality_alternative", "Alternative tested"),
    )
    return [
        f"- {lab.get(lk, fallback)} {_quality_flag_mark(flags.get(fk))}"
        for fk, lk, fallback in rows
    ]


def format_coverage_count_lines(
    coverage: Optional[dict] = None,
    labels: Optional[Dict[str, str]] = None,
) -> List[str]:
    """5/7-style breakdown under Evidence Coverage."""
    lab = labels if isinstance(labels, dict) else {}
    cov = coverage if isinstance(coverage, dict) else {}
    claims = cov.get("claims")
    observed = cov.get("directly_observed")
    timeline = cov.get("timeline_verified")
    metric = cov.get("metric_verified")
    unverified = cov.get("unverified_assumptions")
    if observed is None and claims is None:
        return []
    denom = f"/{claims}" if claims not in (None, "") else ""
    return [
        f"- {lab.get('coverage_observed', 'Directly observed')} {observed}",
        f"- {lab.get('coverage_timeline', 'Timeline verified')} "
        f"{timeline}{denom if not str(timeline).count('/') else ''}",
        f"- {lab.get('coverage_metric', 'Metric verified')} "
        f"{metric}{denom if not str(metric).count('/') else ''}",
        f"- {lab.get('coverage_unverified', 'Unverified assumptions')} {unverified}",
    ]


_FOLLOWUP_ASK_RE = re.compile(
    r"^(tell me more|more details?|go on|continue|keep going|"
    r"elaborate|explain more|what else|and then\??|please continue)\.?$",
    re.IGNORECASE,
)


def looks_like_followup_ask(query: str = "") -> bool:
    """True for short conversational follow-ups that should skip scope confirm."""
    return bool(_FOLLOWUP_ASK_RE.match(str(query or "").strip()))


def should_confirm_interpreted_query(
    query: str = "",
    *,
    template_id: str = "",
    already_interpreted: bool = False,
    has_conversation: bool = False,
) -> bool:
    """True when a free-form Ask should show the interpret/scope card first."""
    if already_interpreted or str(template_id or "").strip():
        return False
    if has_conversation:
        return False
    q = str(query or "").strip()
    if not q:
        return False
    if "Investigation scope:" in q and "Interpreted as " in q:
        return False
    if looks_like_followup_ask(q):
        return False
    return True


_COMPARE_PERCENT_ALIASES: Dict[str, str] = {
    "migrations": "migrations",
    "migrated_tasks": "migrations",
    "blocking": "blocking",
    "execution": "execution",
}


def experiment_percents_from_compare(compare: Optional[dict] = None) -> Dict[str, float]:
    """Extract metric → signed percent from compare_performance / Trace Compare."""
    data = compare if isinstance(compare, dict) else {}
    if isinstance(data.get("data"), dict) and not data.get("checks"):
        data = data["data"]
    out: Dict[str, float] = {}

    def _store(raw_key: Any, pct: Any) -> None:
        try:
            value = float(pct)
        except (TypeError, ValueError):
            return
        key = str(raw_key or "").strip().lower().replace(" ", "_")
        if not key:
            return
        alias = _COMPARE_PERCENT_ALIASES.get(key, key)
        out[alias] = value
        if alias != key:
            out[key] = value

    for c in data.get("checks") or []:
        if not isinstance(c, dict):
            continue
        mid = str(c.get("id") or c.get("metric") or "").strip()
        label = str(c.get("label") or "").lower()
        if not mid:
            if "migrat" in label:
                mid = "migrations"
            elif "block" in label:
                mid = "blocking"
            elif "execut" in label:
                mid = "execution"
        detail = str(c.get("detail") or "")
        delta = c.get("delta")
        if delta is None:
            continue
        if "%" in detail:
            _store(mid, delta)
            continue
        try:
            cand = float(c.get("candidate"))
            base = float(c.get("baseline"))
        except (TypeError, ValueError):
            continue
        if base:
            _store(mid, 100.0 * (cand - base) / abs(base))
    for r in data.get("rows") or []:
        if not isinstance(r, dict) or r.get("delta_pct") is None:
            continue
        metric = str(r.get("metric") or "")
        field = str(r.get("field") or "")
        if field and field not in ("count", "total", ""):
            continue
        _store(metric, r.get("delta_pct"))
    return out


_ANNOTATION_LINE_RE = re.compile(
    r"(?im)^(?:annotation|note|mark)\s*[:=]\s*.+$"
)
_ANNOTATION_INLINE_RE = re.compile(
    r'(?i)\b(?:annotation|note)\s*(?:[:=]\s*|"\s*)"[^"]*"'
)


def sanitize_annotations_text(text: str) -> str:
    """Strip annotation note payloads before a cloud send."""
    out = _ANNOTATION_LINE_RE.sub("[annotation]", str(text or ""))
    return _ANNOTATION_INLINE_RE.sub("[annotation]", out)


def falsification_checks(finding: Optional[dict] = None) -> Dict[str, Any]:
    """What evidence would disprove the leading explanation for this finding."""
    blob = _finding_blob(finding).lower()
    title = str((finding or {}).get("title") or "this finding") if finding else "the conclusion"
    checks: List[str] = []
    next_check = "Inspect the strongest jump:TIME on the timeline"
    if "migrat" in blob or "thrash" in blob or "bounc" in blob:
        checks = [
            "No core-to-core hops in the cursor window for the named task",
            "Ping-pong / bounce count is near zero in the scoped Statistics",
            "Another task accounts for the majority of migrations",
        ]
        next_check = "Open Core Migrations / Heatmap around the cited jump:TIME"
    elif "block" in blob or "latency" in blob or "mutex" in blob or "contention" in blob:
        checks = [
            "No corresponding mutex hold episode in the window",
            "Latency spike occurs while the task is runnable (on-CPU)",
            "Another task causes the majority of blocking",
        ]
        next_check = "Inspect mutex hold / Blocking Max around the cited jump:TIME"
    elif "inversion" in blob or "inherit" in blob:
        checks = [
            "No L/M/H geometry or inherit episode in the window",
            "The waiter is not blocked on the suspected mutex",
            "Priority boost duration does not overlap the latency spike",
        ]
        next_check = "Open Priority Inheritance around the cited jump:TIME"
    elif "wcet" in blob or "execution" in blob or "spike" in blob:
        checks = [
            "Max execution slice is in-family with typical (no Max≫Avg)",
            "The long slice is an ISR / TICK, not the named task",
            "Preemption, not payload, stretches the slice",
        ]
        next_check = "Jump to Execution Max and confirm the task row"
    elif "tick" in blob or "missed" in blob:
        checks = [
            "Tick CV is below the 5% threshold in this scope",
            "Large gaps are idle (tickless), not missed ticks under load",
        ]
        next_check = "Open Trace Health (TICK) for the scoped window"
    elif "load" in blob or "imbalance" in blob or "balance" in blob:
        checks = [
            "Load Balance Score is in the green zone for this window",
            "Concurrent-active distribution is even across cores",
        ]
        next_check = "Open Core Utilisation / Load Balance Score"
    else:
        checks = [
            "Cited jump:TIME is outside the cursor region",
            "Named task does not appear in scoped Statistics",
            "The metric named in the conclusion is not present",
        ]
    return {
        "conclusion": title,
        "would_disprove": checks,
        "disprove": checks,
        "supporting": [],
        "next_check": next_check,
    }


NEXT_STEP_KINDS: Tuple[str, ...] = (
    "investigate", "verify", "scope", "statistics", "compare",
    "experiment", "follow_up",
)
NEXT_STEP_LIMIT_DEFAULT = 3
NEXT_STEP_LIMIT_MAX = 3
_STATS_NEXT_HINTS = (
    "mutex", "blocking", "migration", "heatmap", "priority", "inheritance",
    "utilisation", "utilization", "load balance", "tick", "execution max",
    "statistics", "core util",
)
_EXPERIMENT_TOOLS = frozenset({
    "what_if", "optimize", "optimize_experiment", "recommend_experiments",
})


def _next_step_limit(raw: Any) -> int:
    try:
        n = int(raw)
    except (TypeError, ValueError):
        n = NEXT_STEP_LIMIT_DEFAULT
    return max(0, min(NEXT_STEP_LIMIT_MAX, n))


def _completed_tool_names(payload: Optional[dict] = None) -> List[str]:
    data = payload if isinstance(payload, dict) else {}
    case = data.get("investigation_case") if isinstance(
        data.get("investigation_case"), dict) else {}
    names: List[str] = []
    for src in (
        case.get("tools_executed"),
        data.get("tools_executed"),
        data.get("tools_used"),
        data.get("tools_run"),
    ):
        if not isinstance(src, (list, tuple)):
            continue
        for item in src:
            name = ""
            if isinstance(item, dict):
                name = str(item.get("name") or item.get("tool") or "").strip()
            else:
                name = str(item or "").strip()
            if name and name not in names:
                names.append(name)
    return names


def _coverage_percent(payload: Optional[dict] = None) -> int:
    data = payload if isinstance(payload, dict) else {}
    cov = data.get("coverage") if isinstance(data.get("coverage"), dict) else None
    if cov is None:
        cov = data.get("evidence_coverage") if isinstance(
            data.get("evidence_coverage"), dict) else {}
    try:
        return max(0, min(100, int(cov.get("percent") or 0)))
    except (TypeError, ValueError):
        return 0


def _missing_evidence_items(payload: Optional[dict] = None) -> List[str]:
    data = payload if isinstance(payload, dict) else {}
    falsify = data.get("falsification") if isinstance(
        data.get("falsification"), dict) else None
    if falsify is None:
        falsify = data.get("falsify") if isinstance(data.get("falsify"), dict) else {}
    out: List[str] = []
    for src in (
        falsify.get("would_disprove"),
        falsify.get("disprove"),
        data.get("missing_evidence"),
    ):
        if not isinstance(src, (list, tuple)):
            continue
        for item in src:
            text = str(item or "").strip()
            if text and text not in out:
                out.append(text)
    return out


def _prose_next_check(payload: Optional[dict] = None) -> str:
    data = payload if isinstance(payload, dict) else {}
    falsify = data.get("falsification") if isinstance(
        data.get("falsification"), dict) else None
    if falsify is None:
        falsify = data.get("falsify") if isinstance(data.get("falsify"), dict) else {}
    return str(falsify.get("next_check") or data.get("recommended_action") or "").strip()


_MATERIAL_FINDING_SEV = frozenset({
    "warning", "error", "critical", "high", "warn",
})


def _finding_dicts(raw: Any) -> List[Dict[str, Any]]:
    src = raw if isinstance(raw, (list, tuple)) else []
    return [f for f in src if isinstance(f, dict) and (
        str(f.get("id") or "").strip() or str(f.get("title") or "").strip()
    )]


def _primary_finding_keys(payload: Optional[dict] = None) -> set:
    data = payload if isinstance(payload, dict) else {}
    keys: set = set()
    for src in (
        data.get("finding") if isinstance(data.get("finding"), dict) else {},
        (data.get("investigation_case") or {}).get("finding")
        if isinstance(data.get("investigation_case"), dict) else {},
    ):
        if not isinstance(src, dict):
            continue
        fid = str(src.get("id") or "").strip().lower()
        title = str(src.get("title") or "").strip().lower()
        if fid:
            keys.add(fid)
        if title:
            keys.add(title)
    return keys


def remaining_analysis_findings(
    payload: Optional[dict] = None,
    findings: Any = None,
) -> List[Dict[str, Any]]:
    """Warning/error findings not covered by the current Investigation Case."""
    data = payload if isinstance(payload, dict) else {}
    items = _finding_dicts(findings)
    if not items:
        items = _finding_dicts(data.get("analysis_findings"))
    if not items:
        items = _finding_dicts(data.get("findings"))
    skip = _primary_finding_keys(data)
    out: List[Dict[str, Any]] = []
    seen: set = set()
    for finding in items:
        fid = str(finding.get("id") or "").strip()
        title = str(finding.get("title") or "").strip()
        key = (fid or title).lower()
        if not key or key in seen or key in skip:
            continue
        if title.lower() in skip:
            continue
        sev = str(finding.get("severity") or "").strip().lower()
        if sev and sev not in _MATERIAL_FINDING_SEV:
            continue
        seen.add(key)
        out.append(finding)
    return out


def _finding_follow_up_step(finding: Dict[str, Any]) -> Dict[str, str]:
    fid = str(finding.get("id") or "").strip()
    title = str(finding.get("title") or fid or "this finding").strip()
    task = str(finding.get("task") or "").strip()
    nxt = str(falsification_checks(finding).get("next_check") or "").strip()
    focus = f" for {task}" if task else ""
    id_bit = f" (id={fid})" if fid else ""
    prompt = f"Investigate remaining finding {title}{id_bit}{focus}. "
    if nxt:
        prompt += f"{nxt} "
    if fid:
        prompt += f"Call investigate(finding_id={fid}) if more evidence is needed. "
    prompt += "Preserve the current Investigation Case, Context, and Scope."
    kind = "statistics" if _looks_like_stats_check(nxt) else "investigate"
    return {
        "label": (title or _short_next_label(nxt))[:80],
        "prompt": prompt.strip(),
        "reason": nxt or f"Remaining finding {fid or title}",
        "kind": kind,
    }


def _short_next_label(text: str, fallback: str = "Next check") -> str:
    src = re.sub(r"\s+", " ", str(text or "").strip())
    if not src:
        return fallback
    src = re.sub(r"^[.►▶\-\s]+", "", src)
    if len(src) <= 48:
        return src.rstrip(".")
    cut = src[:48]
    sp = cut.rfind(" ")
    if sp >= 20:
        cut = cut[:sp]
    return cut.rstrip(".,;:") + "…"


def _looks_like_stats_check(text: str) -> bool:
    blob = str(text or "").lower()
    return any(h in blob for h in _STATS_NEXT_HINTS)


def normalize_next_steps(
    raw: Any = None,
    *,
    limit: Any = NEXT_STEP_LIMIT_DEFAULT,
) -> List[Dict[str, str]]:
    """Clip and validate 0–3 next-step dicts (label, prompt, reason, kind)."""
    cap = _next_step_limit(limit if limit is not None else NEXT_STEP_LIMIT_DEFAULT)
    if cap <= 0:
        return []
    src = raw if isinstance(raw, (list, tuple)) else []
    out: List[Dict[str, str]] = []
    seen: set = set()
    for item in src:
        if len(out) >= cap:
            break
        if not isinstance(item, dict):
            continue
        prompt = str(item.get("prompt") or "").strip()
        if not prompt:
            continue
        key = prompt.casefold()
        if key in seen:
            continue
        seen.add(key)
        kind = str(item.get("kind") or "follow_up").strip().lower().replace("-", "_")
        if kind not in NEXT_STEP_KINDS:
            kind = "follow_up"
        label = str(item.get("label") or "").strip() or _short_next_label(prompt)
        reason = str(item.get("reason") or "").strip()
        out.append({
            "label": label[:80],
            "prompt": prompt,
            "reason": reason,
            "kind": kind,
        })
    return out


def compute_next_steps(
    payload: Optional[dict] = None,
    *,
    limit: Any = NEXT_STEP_LIMIT_DEFAULT,
    loaded_tab_count: Any = 1,
    findings: Any = None,
) -> Dict[str, Any]:
    """Host next-step prompts from the current Investigation Case (read-only)."""
    cap = _next_step_limit(limit if limit is not None else NEXT_STEP_LIMIT_DEFAULT)
    data = payload if isinstance(payload, dict) else {}
    try:
        tabs = int(loaded_tab_count)
    except (TypeError, ValueError):
        tabs = 1
    completed = {n.lower() for n in _completed_tool_names(data)}
    cov = _coverage_percent(data)
    missing = _missing_evidence_items(data)
    nxt = _prose_next_check(data)
    conf = str(data.get("confidence") or "").strip().lower()
    finding = data.get("finding") if isinstance(data.get("finding"), dict) else {}
    case = data.get("investigation_case") if isinstance(
        data.get("investigation_case"), dict) else {}
    title = str(
        data.get("conclusion") or finding.get("title") or case.get("goal") or ""
    ).strip()
    task = str(finding.get("task") or data.get("task") or case.get("task") or "").strip()
    focus = f" for {task}" if task else ""
    subject = title or "the current finding"
    remaining = remaining_analysis_findings(data, findings)

    if cap <= 0:
        return {"steps": [], "stop_reason": "No further check requested."}
    case_complete = cov >= 80 and not missing and conf in ("high", "medium")
    if case_complete and not remaining:
        return {
            "steps": [],
            "stop_reason": "Evidence is sufficient; no further check is required.",
        }

    steps: List[Dict[str, str]] = []

    def _add(kind: str, label: str, prompt: str, reason: str) -> None:
        if len(steps) >= cap:
            return
        blob = prompt.casefold()
        if any(blob == str(s.get("prompt") or "").casefold() for s in steps):
            return
        steps.append({
            "label": label[:80],
            "prompt": prompt,
            "reason": reason,
            "kind": kind if kind in NEXT_STEP_KINDS else "follow_up",
        })

    if not case_complete and missing and "verify_claim" not in completed:
        gap = missing[0]
        _add(
            "verify",
            "Verify missing evidence",
            (
                f"Verify the leading explanation{focus}. Missing evidence: {gap}. "
                "Stay in the current Investigation Case, Context, and Scope. "
                "Call verify_claim and collect query_raw_metric / correlate_events "
                "only if another result could change the verdict."
            ),
            gap,
        )
    elif missing:
        gap = missing[0]
        _add(
            "investigate",
            "Collect missing evidence",
            (
                f"Collect evidence for {subject}{focus}. Missing: {gap}. "
                "Preserve the current Scope. Call correlate_events or "
                "query_raw_metric for any missing jump:TIME values."
            ),
            gap,
        )

    if not case_complete and nxt:
        kind = "statistics" if _looks_like_stats_check(nxt) else "follow_up"
        if kind != "experiment" or cov >= 40:
            _add(
                kind,
                _short_next_label(nxt),
                (
                    f"{nxt} Preserve the current Investigation Case, Context, "
                    "and Scope."
                ),
                "Recommended next check from the current case.",
            )

    if not case_complete and cov < 40 and "investigate" not in completed:
        _add(
            "investigate",
            "Collect scoped evidence",
            (
                f"Investigate {subject}{focus} in the current scope. "
                "Call investigate, then correlate_events / query_raw_metric "
                "for missing jump:TIME values. Do not change Scope."
            ),
            "Evidence coverage is still missing.",
        )

    if not case_complete and tabs >= 2 and "compare_performance" not in completed:
        _add(
            "compare",
            "Compare traces",
            (
                "Compare Trace A vs Trace B in the current compare scope. "
                "Call compare_performance. Preserve direction A − B. "
                "Do not switch to Full Trace unless the user asks."
            ),
            "A second trace is loaded and comparison has not been run.",
        )

    if (
        not case_complete
        and cov >= 40
        and conf in ("high", "medium")
        and not (completed & _EXPERIMENT_TOOLS)
        and not missing
    ):
        _add(
            "experiment",
            "Validate with a what-if",
            (
                "If the leading explanation is supported, call what_if or "
                "recommend_experiments for one validation experiment. "
                "Preserve the current Scope."
            ),
            "Evidence is sufficient to consider a validation experiment.",
        )

    for extra in remaining:
        step = _finding_follow_up_step(extra)
        _add(
            str(step.get("kind") or "investigate"),
            str(step.get("label") or ""),
            str(step.get("prompt") or ""),
            str(step.get("reason") or ""),
        )

    if not steps and nxt:
        _add("follow_up", _short_next_label(nxt), nxt, "")
    if not steps and title:
        _add(
            "follow_up",
            "Inspect cited evidence",
            (
                "Inspect the strongest jump:TIME on the timeline in the current "
                "scope and report whether it supports the leading explanation. "
                "Preserve the current Investigation Case and Scope."
            ),
            "No unused structured check remained.",
        )
    if not steps:
        return {
            "steps": [],
            "stop_reason": "No unused follow-up check remains.",
        }
    return {"steps": normalize_next_steps(steps, limit=cap), "stop_reason": None}


def extract_claims(
    text: str,
    *,
    known_tasks: Optional[Sequence[str]] = None,
    known_metrics: Optional[Sequence[str]] = None,
    cursor_lo: Optional[float] = None,
    cursor_hi: Optional[float] = None,
) -> List[Dict[str, Any]]:
    """Pull task names, metrics, and jump:TIME values out of a reply."""
    src = str(text or "")
    tasks = {str(t).strip() for t in (known_tasks or []) if str(t).strip()}
    tasks_l = {t.lower(): t for t in tasks}
    metrics = {
        str(m).strip().lower() for m in (known_metrics or _KNOWN_METRICS) if str(m).strip()
    }
    claims: List[Dict[str, Any]] = []
    seen: set = set()

    def add(kind: str, value: Any, *, ok: bool, detail: str = "") -> None:
        key = (kind, str(value))
        if key in seen:
            return
        seen.add(key)
        claims.append({"kind": kind, "value": value, "ok": ok, "detail": detail})

    for m in _JUMP_RE.finditer(src):
        try:
            t = float(m.group(1))
        except ValueError:
            continue
        in_scope = True
        detail = ""
        if cursor_lo is not None and t < float(cursor_lo):
            in_scope = False
            detail = "timestamp before cursor window"
        if cursor_hi is not None and t > float(cursor_hi):
            in_scope = False
            detail = "timestamp after cursor window"
        add("jump", t, ok=in_scope, detail=detail)

    for m in _TASK_NAME_RE.finditer(src):
        name = m.group(1)
        if tasks:
            ok = name.lower() in tasks_l
            add("task", name, ok=ok, detail="" if ok else "task not in trace/findings")
        else:
            add("task", name, ok=True, detail="no known-task list; accepted")

    low = src.lower()
    for metric in sorted(metrics):
        if re.search(r"\b" + re.escape(metric) + r"\b", low):
            add("metric", metric, ok=True)

    return claims


def validate_ai_response(
    text: str,
    *,
    known_tasks: Optional[Sequence[str]] = None,
    known_metrics: Optional[Sequence[str]] = None,
    known_times: Optional[Sequence[float]] = None,
    cursor_lo: Optional[float] = None,
    cursor_hi: Optional[float] = None,
    tool_results: Optional[Sequence[dict]] = None,
    allow_estimates: bool = True,
) -> Dict[str, Any]:
    """Host-side hallucination guard for an assistant reply."""
    claims = extract_claims(
        text,
        known_tasks=known_tasks,
        known_metrics=known_metrics,
        cursor_lo=cursor_lo,
        cursor_hi=cursor_hi,
    )
    times = set()
    for t in known_times or []:
        try:
            times.add(float(t))
        except (TypeError, ValueError):
            continue
    for res in tool_results or []:
        if not isinstance(res, dict):
            continue
        data = res.get("data") if isinstance(res.get("data"), dict) else res
        for key in ("evidence", "events", "path"):
            for item in data.get(key) or []:
                if isinstance(item, dict) and item.get("time") is not None:
                    try:
                        times.add(float(item.get("time")))
                    except (TypeError, ValueError):
                        continue
    flags: List[str] = []
    unverified = 0
    for c in claims:
        if c.get("kind") == "jump" and times:
            try:
                val = float(c.get("value"))
            except (TypeError, ValueError):
                continue
            if val not in times and not any(abs(val - t) < 1e-6 for t in times):
                # Still ok if it is inside the cursor window and tools didn't
                # enumerate every timestamp — only flag when out of scope.
                if not c.get("ok"):
                    unverified += 1
                    flags.append(f"jump:{c['value']} outside cursor window")
        elif c.get("kind") == "task" and not c.get("ok"):
            unverified += 1
            flags.append(f"unknown task {c.get('value')}")
        elif not c.get("ok"):
            unverified += 1
            flags.append(str(c.get("detail") or c.get("kind")))
    low = str(text or "").lower()
    if not allow_estimates:
        if "what_if" in low or "optimize_experiment" in low:
            if "estimate" not in low and "heuristic" not in low:
                flags.append("simulator result not labelled as an estimate")
                unverified += 1
    ok = unverified == 0
    return {
        "ok": ok,
        "claims": claims,
        "unverified": unverified,
        "flags": flags,
        "message": (
            "All extracted claims match trace scope"
            if ok else
            f"{unverified} claim(s) could not be verified against trace data"
        ),
    }


def interpret_investigation_query(
    question: str,
    *,
    findings: Optional[Sequence[dict]] = None,
    cursor_lo: Optional[float] = None,
    cursor_hi: Optional[float] = None,
) -> Dict[str, Any]:
    """Turn a free-form question into an explicit investigation scope."""
    q = str(question or "").strip()
    blob = q.lower()
    items = [f for f in (findings or []) if isinstance(f, dict)]
    kind = "diagnose"
    scopes = ["execution", "blocking"]
    if any(w in blob for w in ("compar", "regress", "vs ", "versus", "before", "after")):
        kind = "compare"
        scopes = ["execution", "blocking", "migrations", "tick"]
    elif any(w in blob for w in ("optimi", "faster", "improve", "what-if", "what if", "pin")):
        kind = "optimize"
        scopes = ["migrations", "blocking", "execution"]
    elif any(w in blob for w in ("report", "write-up", "summary for")):
        kind = "report"
        scopes = ["findings"]
    elif any(w in blob for w in ("why", "cause", "root", "investigat", "slow")):
        kind = "diagnose"
        scopes = ["execution", "blocking", "migrations", "priority inheritance"]
    elif any(w in blob for w in ("what", "explain", "triage")):
        kind = "quick"
        scopes = ["findings"]
    if "migrat" in blob or "thrash" in blob:
        if "migrations" not in scopes:
            scopes.append("migrations")
    if "mutex" in blob or "lock" in blob or "invert" in blob:
        if "priority inheritance" not in scopes:
            scopes.append("priority inheritance")
    focus = None
    if items:
        focus = items[0]
        qlow = blob
        for f in items:
            title = str(f.get("title") or "").lower()
            task = str(f.get("task") or "").lower()
            if title and title in qlow:
                focus = f
                break
            if task and task in qlow:
                focus = f
                break
    window = None
    if cursor_lo is not None and cursor_hi is not None:
        window = {"lo": cursor_lo, "hi": cursor_hi}
    mode = kind if kind in INVESTIGATION_MODES else "diagnose"
    return {
        "ok": True,
        "interpreted_question": q or "Investigate the main performance problem",
        "kind": kind,
        "mode": mode,
        "scope": scopes,
        "finding_id": str((focus or {}).get("id") or ""),
        "task": str((focus or {}).get("task") or ""),
        "cursor_window": window,
        "suggested_tools": investigation_mode_plan(mode).get("tools") or [],
        "message": f"Interpreted as {kind} investigation",
    }


def explain_finding_payload(
    finding: Optional[dict],
    *,
    level: str = "technical",
    hypotheses: Optional[Sequence[dict]] = None,
) -> Dict[str, Any]:
    """Three-level explanation of one Analysis Finding (host-side)."""
    lv = str(level or "technical").strip().lower()
    if lv not in EXPLAIN_LEVELS:
        lv = "technical"
    if not isinstance(finding, dict):
        return {"ok": False, "message": "No finding selected", "level": lv}
    title = str(finding.get("title") or finding.get("id") or "Finding")
    text = str(finding.get("text") or "")
    sev = str(finding.get("severity") or "info")
    task = str(finding.get("task") or "")
    hyps = enrich_hypotheses(hypotheses or [], evidence=finding.get("evidence") or [])
    quick = f"{sev.upper()}: {title}." + (f" Focus task {task}." if task else "")
    technical = (
        f"{title} ({sev}). {text} "
        "Confirm the named Statistics section, then click Max / a scatter "
        "point to seek the timeline."
    ).strip()
    deep = technical
    if hyps:
        names = "; ".join(
            f"{h['hypothesis']} [{h['status']}]" for h in hyps[:4]
        )
        deep = (
            f"{technical} Leading hypotheses: {names}. "
            "Call investigate → correlate_events → find_critical_path → "
            "build_task_dependency_graph → analyze_temporal_causality → "
            "rank_root_causes → challenge_conclusion, "
            "then verify jump:TIME inside the cursor window."
        )
    body = {"quick": quick, "technical": technical, "deep": deep}[lv]
    return {
        "ok": True,
        "message": f"{lv} explanation of {finding.get('id') or title}",
        "level": lv,
        "finding": {
            "id": finding.get("id"),
            "severity": sev,
            "title": title,
            "text": text,
            "task": task,
            "evidence": list(finding.get("evidence") or []),
        },
        "hypotheses": hyps,
        "explanation": body,
        "levels": {
            "quick": quick,
            "technical": technical,
            "deep": deep,
        },
    }


def investigation_mode_plan(mode: str = "diagnose") -> Dict[str, Any]:
    """User-facing investigation mode → goal + tool sequence."""
    want = str(mode or "diagnose").strip().lower()
    if want not in INVESTIGATION_MODES:
        want = "diagnose"
    plans = {
        "quick": {
            "goal": "Find the most likely problem",
            "tools": ["detect_anomalies", "investigate"],
            "template": "triage",
        },
        "diagnose": {
            "goal": "Find cause → gather evidence → verify",
            "tools": [
                "investigate", "correlate_events", "find_critical_path",
                "build_task_dependency_graph", "analyze_temporal_causality",
                "rank_root_causes", "challenge_conclusion",
            ],
            "template": "investigate",
        },
        "compare": {
            "goal": "Explain why A differs from B",
            "tools": ["compare_performance", "regression_explain"],
            "template": "compare",
        },
        "optimize": {
            "goal": "Find cause → propose experiments → rank them",
            "tools": [
                "investigate", "what_if", "optimize_experiment",
                "recommend_experiments",
            ],
            "template": "optimize",
        },
        "report": {
            "goal": "Turn confirmed findings into an engineering report",
            "tools": ["generate_report", "export_report"],
            "template": "diagnostic_report",
        },
    }
    plan = dict(plans[want])
    plan["mode"] = want
    plan["ok"] = True
    return plan


INVESTIGATION_MODE_LABELS: Dict[str, str] = {
    "quick": "Quick",
    "diagnose": "Diagnose",
    "compare": "Compare",
    "optimize": "Optimize",
    "report": "Report",
}


def investigation_mode_prompt(mode: str = "diagnose") -> str:
    """User prompt for an Investigation Mode chip (maps onto existing tools)."""
    plan = investigation_mode_plan(mode)
    listed = "; ".join(str(t) for t in (plan.get("tools") or []) if t)
    label = INVESTIGATION_MODE_LABELS.get(plan["mode"], plan["mode"])
    if plan["mode"] == "report":
        return (
            f"{plan.get('goal') or label}. Call generate_report, then "
            "export_report (format html unless the user asked for csv). "
            "Include only supported sections and mark missing requested "
            "evidence as Not evaluated. Saving the file is required — do not "
            "stop after generate_report alone."
        )
    return (
        f"{plan.get('goal') or label}. Preferred tools: {listed}. "
        "Start with the first applicable tool, then continue only if another "
        "result could change the verdict. Do not call unavailable or irrelevant "
        "tools. Call manage_hypotheses only when a hypothesis status changes. "
        "Finish with a verdict, jump:TIME evidence, what would disprove this, "
        "confidence, and one next check."
    )


def parse_user_investigation_templates(raw: Any) -> List[Dict[str, Any]]:
    """Deserialize user-saved investigation sequences."""
    if isinstance(raw, list):
        items = raw
    else:
        try:
            items = json.loads(str(raw or "") or "[]")
        except json.JSONDecodeError:
            return []
    out: List[Dict[str, Any]] = []
    if not isinstance(items, list):
        return out
    for i, it in enumerate(items):
        if not isinstance(it, dict):
            continue
        label = str(it.get("label") or "").strip()
        steps = [str(s).strip() for s in (it.get("steps") or []) if str(s).strip()]
        if not label or not steps:
            continue
        tid = str(it.get("id") or "").strip()
        if not tid:
            tid = re.sub(r"[^a-z0-9]+", "_", label.lower()).strip("_") or f"user_{i + 1}"
        out.append({
            "id": tid, "label": label, "steps": steps, "user": True,
        })
    return out


def dump_user_investigation_templates(items: Optional[Sequence[dict]] = None) -> str:
    rows = []
    for it in items or []:
        if not isinstance(it, dict):
            continue
        label = str(it.get("label") or "").strip()
        steps = [str(s).strip() for s in (it.get("steps") or []) if str(s).strip()]
        if not label or not steps:
            continue
        tid = str(it.get("id") or "").strip() or re.sub(
            r"[^a-z0-9]+", "_", label.lower()).strip("_")
        rows.append({"id": tid, "label": label, "steps": steps})
    return json.dumps(rows, ensure_ascii=False)


def new_user_investigation_template(
    label: str,
    steps: Optional[Sequence[str]] = None,
) -> Dict[str, Any]:
    name = str(label or "").strip() or "My Investigation"
    seq = [str(s).strip() for s in (steps or []) if str(s).strip()]
    if not seq:
        seq = list(investigation_mode_plan("diagnose").get("tools") or ["investigate"])
    tid = re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_") or "user"
    return {"id": tid, "label": name, "steps": seq, "user": True}


VALIDATE_EXPERIMENT_PROMPT = (
    "Did this before/after capture validate the experiment? "
    "Call validate_experiment. Omit actual — the host fills percents from "
    "the last Trace Compare (Limit to C1–Cn honored when each tab has 2+ cursors). "
    "If expected deltas "
    "are known from what_if or optimize_experiment, pass them as expected; "
    "otherwise omit expected. Then report VALIDATED, PARTIALLY VALIDATED, "
    "or DISPROVED with supporting evidence and one next check."
)


def validate_experiment(
    expected: Optional[dict] = None,
    actual: Optional[dict] = None,
) -> Dict[str, Any]:
    """Compare expected experiment deltas with Trace Compare / what-if actuals.

    *expected* / *actual* maps metric → signed percent (negative = improvement
    for cost-like metrics such as migrations / blocking).
    """
    exp = expected if isinstance(expected, dict) else {}
    act = actual if isinstance(actual, dict) else {}
    rows: List[Dict[str, Any]] = []
    matched = 0
    disagreed = 0
    for key in sorted(set(list(exp.keys()) + list(act.keys()))):
        e = exp.get(key)
        a = act.get(key)
        try:
            e_n = float(e) if e is not None else None
        except (TypeError, ValueError):
            e_n = None
        try:
            a_n = float(a) if a is not None else None
        except (TypeError, ValueError):
            a_n = None
        status = "missing"
        if e_n is None and a_n is None:
            status = "missing"
        elif e_n is None:
            status = "unspecified"
        elif a_n is None:
            status = "unmeasured"
        else:
            same_dir = (e_n == 0 and abs(a_n) < 5) or (e_n * a_n > 0) or (
                abs(e_n) < 5 and abs(a_n) < 8
            )
            close = abs(a_n - e_n) <= max(10.0, abs(e_n) * 0.5)
            if same_dir and close:
                status = "validated"
                matched += 1
            elif same_dir:
                status = "partial"
                matched += 1
            else:
                status = "disproved"
                disagreed += 1
        rows.append({
            "metric": str(key),
            "expected": e_n,
            "actual": a_n,
            "status": status,
        })
    if not rows:
        result = "INCONCLUSIVE"
    elif disagreed and matched:
        result = "PARTIALLY VALIDATED"
    elif disagreed:
        result = "DISPROVED"
    elif matched:
        result = "VALIDATED"
    else:
        result = "INCONCLUSIVE"
    return {
        "ok": True,
        "result": result,
        "rows": rows,
        "matched": matched,
        "disagreed": disagreed,
        "message": f"Experiment {result}",
    }


def record_confidence_step(
    history: Optional[Sequence[dict]],
    *,
    tool_name: str,
    score: Any = None,
    band: str = "",
    note: str = "",
) -> List[Dict[str, Any]]:
    """Append one confidence-evolution step (audit trail)."""
    out = [dict(s) for s in (history or []) if isinstance(s, dict)]
    entry: Dict[str, Any] = {
        "tool": str(tool_name or "").strip(),
        "note": str(note or "").strip(),
    }
    if score is not None:
        entry["score"] = max(0, min(100, _safe_int(score)))
        entry["band"] = band or evidence_quality_band(score)
    elif band:
        entry["band"] = band
    out.append(entry)
    return out


def format_confidence_evolution(history: Optional[Sequence[dict]]) -> str:
    lines: List[str] = []
    for i, step in enumerate(history or []):
        if not isinstance(step, dict):
            continue
        tool = str(step.get("tool") or f"step {i + 1}")
        if i == 0:
            prefix = "Initial"
        else:
            prefix = f"After {tool}"
        band = str(step.get("band") or "")
        score = step.get("score")
        extra = f" {score}%" if score is not None else ""
        note = str(step.get("note") or "")
        label = f"{prefix}: {band}{extra}".strip()
        if note:
            label += f" — {note}"
        lines.append(label)
    return "\n".join(lines)


def tool_call_reason(tool_name: str, finding: Optional[dict] = None) -> str:
    """Why the host / model would call this tool for the current finding."""
    name = str(tool_name or "").strip()
    base = _TOOL_REASONS.get(name, f"Run {name} as part of the investigation plan")
    blob = _finding_blob(finding)
    if blob:
        title = str((finding or {}).get("title") or "").strip()
        if title:
            return f"{base}. Finding: {title}."
    return base


AI_SPLIT_BOTTOM_DEFAULT = 80
AI_SPLIT_BOTTOM_MIN = 64
AI_SPLIT_BOTTOM_MAX = 400


def clamp_ai_split_bottom(raw: Any) -> int:
    """Composer-pane height for the AI log splitter (px)."""
    try:
        n = int(float(str(raw).strip()))
    except (TypeError, ValueError):
        n = AI_SPLIT_BOTTOM_DEFAULT
    if n <= 0:
        n = AI_SPLIT_BOTTOM_DEFAULT
    return max(AI_SPLIT_BOTTOM_MIN, min(AI_SPLIT_BOTTOM_MAX, n))


def empty_cost_meter() -> Dict[str, Any]:
    return {
        "prompt_tokens": 0,
        "completion_tokens": 0,
        "total_tokens": 0,
        "tool_calls": 0,
        "trace_queries": 0,
        "model_time_s": 0.0,
        "estimated_usd": 0.0,
    }


def accumulate_cost(
    meter: Optional[dict],
    *,
    prompt_tokens: int = 0,
    completion_tokens: int = 0,
    tool_calls: int = 0,
    trace_queries: int = 0,
    model_time_s: float = 0.0,
    usd_per_1k: float = 0.0,
) -> Dict[str, Any]:
    out = dict(meter or empty_cost_meter())
    pt = max(0, _safe_int(prompt_tokens))
    ct = max(0, _safe_int(completion_tokens))
    out["prompt_tokens"] = _safe_int(out.get("prompt_tokens")) + pt
    out["completion_tokens"] = _safe_int(out.get("completion_tokens")) + ct
    out["total_tokens"] = out["prompt_tokens"] + out["completion_tokens"]
    out["tool_calls"] = _safe_int(out.get("tool_calls")) + max(0, _safe_int(tool_calls))
    out["trace_queries"] = _safe_int(out.get("trace_queries")) + max(
        0, _safe_int(trace_queries))
    try:
        out["model_time_s"] = round(
            float(out.get("model_time_s") or 0) + max(0.0, float(model_time_s or 0)),
            3,
        )
    except (TypeError, ValueError):
        pass
    added = (pt + ct) / 1000.0 * max(0.0, float(usd_per_1k or 0))
    try:
        out["estimated_usd"] = round(float(out.get("estimated_usd") or 0) + added, 6)
    except (TypeError, ValueError):
        out["estimated_usd"] = round(added, 6)
    return out


def format_cost_meter(meter: Optional[dict]) -> str:
    m = meter if isinstance(meter, dict) else empty_cost_meter()
    usd = float(m.get("estimated_usd") or 0)
    usd_s = f"${usd:.3f}" if usd else "—"
    return (
        f"Context {m.get('total_tokens') or 0} tokens · "
        f"Tool calls {m.get('tool_calls') or 0} · "
        f"Trace queries {m.get('trace_queries') or 0} · "
        f"Model time {m.get('model_time_s') or 0}s · "
        f"Est. {usd_s}"
    )


def _format_token_count(n: Any) -> str:
    try:
        count = int(n or 0)
    except (TypeError, ValueError):
        count = 0
    if count >= 1000:
        compact = f"{count / 1000.0:.1f}".rstrip("0").rstrip(".")
        return f"{compact}k"
    return str(count)


def format_cost_status(meter: Optional[dict]) -> str:
    """One-line status suffix: ``1.3k tok · 2 tools · 1.5s``."""
    m = meter if isinstance(meter, dict) else empty_cost_meter()
    try:
        tokens = int(m.get("total_tokens") or 0)
    except (TypeError, ValueError):
        tokens = 0
    try:
        tools = int(m.get("tool_calls") or 0)
    except (TypeError, ValueError):
        tools = 0
    try:
        time_s = float(m.get("model_time_s") or 0)
    except (TypeError, ValueError):
        time_s = 0.0
    try:
        usd = float(m.get("estimated_usd") or 0)
    except (TypeError, ValueError):
        usd = 0.0
    parts = [
        f"{_format_token_count(tokens)} tok",
        f"{tools} tools",
        f"{time_s:g}s" if time_s else "0s",
    ]
    if usd:
        parts.append(f"${usd:.3f}")
    return " · ".join(parts)


def cost_meter_active(meter: Optional[dict]) -> bool:
    """True when the conversation has accumulated any billable usage."""
    m = meter if isinstance(meter, dict) else empty_cost_meter()
    try:
        tokens = int(m.get("total_tokens") or 0)
    except (TypeError, ValueError):
        tokens = 0
    try:
        tools = int(m.get("tool_calls") or 0)
    except (TypeError, ValueError):
        tools = 0
    try:
        time_s = float(m.get("model_time_s") or 0)
    except (TypeError, ValueError):
        time_s = 0.0
    try:
        usd = float(m.get("estimated_usd") or 0)
    except (TypeError, ValueError):
        usd = 0.0
    return tokens > 0 or tools > 0 or time_s > 0 or usd > 0


def status_with_cost(message: str, meter: Optional[dict] = None) -> str:
    """Append the cost line to an AI status message when usage exists."""
    text = str(message or "").strip()
    if not cost_meter_active(meter):
        return text
    cost = format_cost_status(meter)
    return f"{text} · {cost}" if text else cost


def chat_usage_from_response(body: Any) -> Dict[str, int]:
    """Normalize OpenAI / Gemini ``usage`` objects into token counts."""
    usage = body.get("usage") if isinstance(body, dict) else None
    if not isinstance(usage, dict):
        return {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
    pt = _safe_int(
        usage.get("prompt_tokens") or usage.get("prompt_token_count") or 0)
    ct = _safe_int(
        usage.get("completion_tokens")
        or usage.get("completion_token_count")
        or usage.get("candidates_token_count")
        or 0
    )
    tot = _safe_int(usage.get("total_tokens") or (pt + ct))
    return {"prompt_tokens": pt, "completion_tokens": ct, "total_tokens": tot}


def format_privacy_chip(priv: Optional[dict] = None) -> str:
    level = str((priv or {}).get("level") or "local")
    return {
        "local": "🟢 Local",
        "cloud_safe": "🟡 Cloud",
        "sensitive": "🔴 Sensitive",
    }.get(level, level.replace("_", " ").title())


def investigation_template_prompt(template: Optional[dict] = None) -> str:
    tpl = template if isinstance(template, dict) else {}
    label = str(tpl.get("label") or "Investigation")
    steps = [str(s) for s in (tpl.get("steps") or []) if s]
    listed = "; ".join(steps) if steps else "investigate"
    return (
        f"Run the {label}. Preferred tools: {listed}. "
        "Start with the first applicable tool, then continue only if another "
        "result could change the verdict. Do not call unavailable or irrelevant "
        "tools. Call manage_hypotheses only when a hypothesis status changes. "
        "Finish with a verdict, jump:TIME evidence, what would disprove this, "
        "confidence, and one next check."
    )


def infer_model_capabilities(model_name: str, *, endpoint_is_local: bool = True) -> Dict[str, Any]:
    """Heuristic capability card from the model id (no network)."""
    name = str(model_name or "").strip().lower()
    cloud = (not endpoint_is_local) or any(
        k in name for k in (
            "gpt-", "gemini", "claude", "kimi", "moonshot", "deepseek", "grok", "o1", "o3",
        )
    )
    small = bool(re.search(r"(^|[^\d])([1-3]b)\b", name)) or "mini" in name or "phi" in name
    large_local = bool(re.search(r"([7-9]b|\d{2,}b)\b", name))
    tool_calling = "yes" if (cloud or large_local) else ("partial" if small else "unknown")
    chaining = "yes" if (cloud or large_local) else "partial"
    long_ctx = "yes" if cloud else ("partial" if large_local else "partial")
    reasoning = "yes" if cloud else ("partial" if large_local else "partial")
    recommend = ""
    if small:
        recommend = "qwen2.5:7b (or larger) for Investigation"
    elif cloud:
        recommend = ""
    elif large_local:
        recommend = ""
    return {
        "ok": True,
        "model": str(model_name or "").strip(),
        "chat": "yes",
        "structured_output": "yes" if (cloud or large_local) else "partial",
        "tool_calling": tool_calling,
        "multi_tool_chaining": chaining,
        "long_context": long_ctx,
        "complex_reasoning": reasoning,
        "recommended": recommend,
        "source": "heuristic",
    }


def classify_trace_privacy(
    *,
    endpoint_is_local: bool = True,
    redact_task_names: bool = False,
    sensitive: bool = False,
) -> Dict[str, Any]:
    """Local / cloud-safe / sensitive classification for the current endpoint."""
    if sensitive:
        level = "sensitive"
        cloud_ok = False
        note = "Cloud AI disabled — treat this trace as confidential"
    elif endpoint_is_local:
        level = "local"
        cloud_ok = True
        note = "Raw trace and Findings stay on this machine"
    elif redact_task_names:
        level = "cloud_safe"
        cloud_ok = True
        note = "Task names anonymized; Findings still leave the machine"
    else:
        level = "cloud_safe"
        cloud_ok = True
        note = "Findings / metrics are sent to the configured cloud endpoint"
    return {
        "level": level,
        "cloud_ok": cloud_ok,
        "endpoint_is_local": bool(endpoint_is_local),
        "redact_task_names": bool(redact_task_names),
        "sensitive": bool(sensitive),
        "note": note,
    }


def anonymize_task_name(name: str, mapping: Optional[dict] = None) -> Tuple[str, Dict[str, str]]:
    """Stable Task-N alias. Returns (alias, updated mapping)."""
    src = str(name or "").strip()
    mp = dict(mapping or {})
    if not src:
        return src, mp
    if src in mp:
        return mp[src], mp
    alias = f"Task-{len(mp) + 1}"
    mp[src] = alias
    return alias, mp


def extract_task_names_from_text(text: str) -> List[str]:
    seen: List[str] = []
    for m in _TASK_NAME_RE.findall(str(text or "")):
        if m not in seen:
            seen.append(m)
    return seen


def anonymize_text(
    text: str,
    task_names: Optional[Sequence[str]] = None,
    mapping: Optional[dict] = None,
) -> Tuple[str, Dict[str, str]]:
    """Replace known task names with stable Task-N aliases."""
    src = str(text or "")
    mp = dict(mapping or {})
    names = [str(n).strip() for n in (task_names or []) if str(n).strip()]
    if not names:
        names = extract_task_names_from_text(src)
    names = sorted(set(names), key=len, reverse=True)
    out = src
    for name in names:
        alias, mp = anonymize_task_name(name, mp)
        if name and alias and name in out:
            out = out.replace(name, alias)
    return out, mp


def apply_cloud_privacy(
    findings_text: str = "",
    query: str = "",
    task_names: Optional[Sequence[str]] = None,
    *,
    endpoint_is_local: bool = True,
    redact_task_names: bool = False,
    sensitive: bool = False,
) -> Dict[str, Any]:
    """Block cloud send when sensitive; optionally anonymize task names."""
    priv = classify_trace_privacy(
        endpoint_is_local=endpoint_is_local,
        redact_task_names=redact_task_names,
        sensitive=sensitive,
    )
    blocked = bool(sensitive and not endpoint_is_local)
    text = str(findings_text or "")
    q = str(query or "")
    mapping: Dict[str, str] = {}
    if not endpoint_is_local and not blocked:
        text = sanitize_annotations_text(text)
        q = sanitize_annotations_text(q)
    if redact_task_names and not endpoint_is_local and not blocked:
        names = [str(n).strip() for n in (task_names or []) if str(n).strip()]
        if not names:
            names = extract_task_names_from_text(f"{text}\n{q}")
        text, mapping = anonymize_text(text, names, mapping)
        q, mapping = anonymize_text(q, names, mapping)
    return {
        "ok": not blocked,
        "blocked": blocked,
        "findings_text": text,
        "query": q,
        "mapping": mapping,
        "privacy": priv,
        "note": (
            "Cloud AI disabled — treat this trace as confidential"
            if blocked else priv.get("note") or ""
        ),
    }


def toggle_interpreted_scope(
    interpreted: Optional[dict] = None,
    key: str = "",
    enabled: Optional[bool] = None,
) -> Dict[str, Any]:
    """Flip one investigation-scope flag on an interpret_query payload."""
    out = dict(interpreted) if isinstance(interpreted, dict) else {}
    scopes = [str(s) for s in (out.get("scope") or []) if s]
    k = str(key or "").strip()
    if k:
        on = (k not in scopes) if enabled is None else bool(enabled)
        if on and k not in scopes:
            scopes.append(k)
        if not on:
            scopes = [s for s in scopes if s != k]
        out["scope"] = scopes
    return out


def interpreted_run_prompt(interpreted: Optional[dict] = None) -> str:
    """Prompt for [Run investigation] after the user confirms / edits scope."""
    data = interpreted if isinstance(interpreted, dict) else {}
    question = str(
        data.get("interpreted_question") or data.get("question") or ""
    ).strip() or "Investigate the main performance problem"
    mode = str(data.get("mode") or data.get("kind") or "diagnose")
    scopes = [str(s) for s in (data.get("scope") or []) if s]
    scope_bit = ", ".join(scopes) if scopes else "execution, blocking"
    fid = str(data.get("finding_id") or "").strip()
    extra = f" finding_id={fid}." if fid else ""
    return (
        f"{question}\n\nInterpreted as {mode}. "
        f"Investigation scope: {scope_bit}.{extra} "
        "Call interpret_query only if the question is still ambiguous, "
        "then investigate and verify jump:TIME evidence."
    )


def format_experiment_verdict(result: Any = None) -> str:
    raw = result
    if isinstance(result, dict):
        raw = result.get("result") or result.get("verdict") or ""
    key = str(raw or "").strip().upper()
    return {
        "VALIDATED": "Hypothesis validated",
        "DISPROVED": "Hypothesis disproved",
        "PARTIALLY VALIDATED": "Hypothesis partially validated",
    }.get(key, "Inconclusive")


def apply_experiment_to_hypotheses(
    hypotheses: Optional[Sequence[dict]] = None,
    result: Any = None,
) -> List[Dict[str, Any]]:
    """Mark open hypotheses supported / rejected from a validate_experiment result."""
    raw = result.get("result") if isinstance(result, dict) else result
    key = str(raw or "").strip().upper()
    status = (
        "supported" if key == "VALIDATED"
        else "rejected" if key == "DISPROVED"
        else ""
    )
    out: List[Dict[str, Any]] = []
    for h in hypotheses or []:
        if not isinstance(h, dict):
            continue
        item = dict(h)
        if status and str(item.get("status") or "").lower() in (
            "", "possible", "need_evidence", "needs_evidence", "untested",
        ):
            item["status"] = status
        out.append(item)
    return out


def parse_user_historical_knowledge(raw: Any) -> List[Dict[str, Any]]:
    if isinstance(raw, list):
        items = raw
    else:
        text = str(raw or "").strip()
        if not text:
            return []
        try:
            parsed = json.loads(text)
        except (TypeError, ValueError, json.JSONDecodeError):
            return []
        items = parsed if isinstance(parsed, list) else []
    out: List[Dict[str, Any]] = []
    for it in items:
        if not isinstance(it, dict):
            continue
        task = str(it.get("task") or "").strip()
        issue = str(it.get("issue") or it.get("previous_issue") or it.get("title") or "").strip()
        if not (task or issue):
            continue
        metrics = _metrics_from_mapping(it.get("metrics") if isinstance(it.get("metrics"), dict) else it)
        out.append({
            "task": task,
            "issue": issue,
            "fix": str(it.get("fix") or it.get("known_fix") or "").strip(),
            "build": str(it.get("build") or it.get("last_occurrence") or "").strip(),
            "keywords": list(it.get("keywords") or []),
            "metrics": metrics,
        })
    return out


def dump_user_historical_knowledge(items: Optional[Sequence[dict]] = None) -> str:
    return json.dumps(parse_user_historical_knowledge(list(items or [])), ensure_ascii=False)


def new_user_historical_entry(
    finding: Optional[dict] = None,
    extras: Optional[dict] = None,
) -> Dict[str, Any]:
    f = finding if isinstance(finding, dict) else {}
    extra = extras if isinstance(extras, dict) else {}
    task = str(extra.get("task") or f.get("task") or "").strip()
    issue = str(
        extra.get("issue") or extra.get("title") or f.get("title") or ""
    ).strip() or "Saved finding"
    metrics = _metrics_from_mapping(extra.get("metrics") if isinstance(extra.get("metrics"), dict) else extra)
    if not metrics:
        metrics = _metrics_from_mapping(f)
    return {
        "task": task,
        "issue": issue,
        "fix": str(extra.get("fix") or "").strip(),
        "build": str(extra.get("build") or "").strip(),
        "keywords": [w for w in re.split(r"\W+", issue.lower()) if len(w) > 3][:6],
        "metrics": metrics,
    }


_HISTORICAL_METRIC_KEYS: Tuple[str, ...] = (
    "migrations", "migration_rate", "blocking", "wcet",
)


def _metrics_from_mapping(src: Any) -> Dict[str, float]:
    data = src if isinstance(src, dict) else {}
    out: Dict[str, float] = {}
    for key in _HISTORICAL_METRIC_KEYS:
        try:
            if data.get(key) is None:
                continue
            out[key] = float(data.get(key))
        except (TypeError, ValueError):
            continue
    return out


def rate_flags_from_metrics(
    current: Optional[dict] = None,
    typical: Optional[dict] = None,
) -> List[str]:
    """Typical vs current rate lines (e.g. migrations 47 vs typical 12)."""
    cur = _metrics_from_mapping(current)
    hist = _metrics_from_mapping(typical)
    flags: List[str] = []
    for key in _HISTORICAL_METRIC_KEYS:
        if key not in cur or key not in hist or hist[key] == 0:
            continue
        ratio = cur[key] / hist[key]
        if ratio >= 2.0:
            flags.append(f"{key} {cur[key]:g} vs typical {hist[key]:g} (×{ratio:.1f})")
    return flags


CAPABILITY_CHAT_PROBE = 'Reply with JSON only: {"ok":true}'

CAPABILITY_PROBE_TOOL: Dict[str, Any] = {
    "type": "function",
    "function": {
        "name": "btf_ping",
        "description": "Capability probe. Call this once if you support tools.",
        "parameters": {"type": "object", "properties": {}},
    },
}

CAPABILITY_PROBE_TOOL_PONG: Dict[str, Any] = {
    "type": "function",
    "function": {
        "name": "btf_pong",
        "description": "Second capability probe. Call after btf_ping if you can chain tools.",
        "parameters": {"type": "object", "properties": {}},
    },
}


def capability_probe_body(model: str) -> Dict[str, Any]:
    return {
        "model": str(model or "").strip(),
        "stream": False,
        "messages": [{
            "role": "user",
            "content": (
                "If you can call tools, call btf_ping then btf_pong. "
                "Otherwise reply PONG."
            ),
        }],
        "tools": [CAPABILITY_PROBE_TOOL, CAPABILITY_PROBE_TOOL_PONG],
        "max_tokens": 64,
    }


def structured_output_from_text(text: str) -> bool:
    src = str(text or "").strip()
    if src.startswith("```"):
        src = re.sub(r"^```(?:json)?\s*", "", src, flags=re.IGNORECASE)
        src = re.sub(r"\s*```$", "", src)
    try:
        return isinstance(json.loads(src), dict)
    except (TypeError, ValueError, json.JSONDecodeError):
        m = re.search(r"\{[^{}]+\}", src)
        if not m:
            return False
        try:
            return isinstance(json.loads(m.group(0)), dict)
        except (TypeError, ValueError, json.JSONDecodeError):
            return False


def count_tool_calls(body: Any) -> Optional[int]:
    if not isinstance(body, dict):
        return None
    choices = body.get("choices")
    if not isinstance(choices, list) or not choices:
        return None
    msg = choices[0].get("message") if isinstance(choices[0], dict) else None
    if not isinstance(msg, dict):
        return None
    calls = msg.get("tool_calls")
    n = len(calls) if isinstance(calls, list) else 0
    if msg.get("function_call"):
        n = max(n, 1)
    if n:
        return n
    if str(msg.get("content") or "").strip():
        return 0
    return None


def merge_live_capability(
    cap: Optional[dict] = None,
    *,
    chat_text: str = "",
    tool_body: Any = None,
    tool_ok: Optional[bool] = None,
) -> Dict[str, Any]:
    """Overlay live Test-connection results on the heuristic capability card."""
    out = dict(cap) if isinstance(cap, dict) else {}
    if structured_output_from_text(chat_text):
        out["structured_output"] = "yes"
        out["source"] = "live"
    elif str(chat_text or "").strip():
        out["structured_output"] = "no"
        out["source"] = "live"
    n = count_tool_calls(tool_body) if tool_body is not None else None
    if tool_ok is True or (n is not None and n >= 1):
        out["tool_calling"] = "yes"
        out["multi_tool_chaining"] = "yes" if (n or 0) >= 2 else "partial"
        out["source"] = "live"
    elif tool_ok is False or n == 0:
        out["tool_calling"] = "no"
        out["multi_tool_chaining"] = "no"
        out["source"] = "live"
    return out


def tool_calling_from_chat_response(body: Any) -> Optional[bool]:
    """True if the chat response issued a tool call; False if text-only; None if empty."""
    if not isinstance(body, dict):
        return None
    choices = body.get("choices")
    if not isinstance(choices, list) or not choices:
        return None
    msg = choices[0].get("message") if isinstance(choices[0], dict) else None
    if not isinstance(msg, dict):
        return None
    calls = msg.get("tool_calls") or msg.get("function_call")
    if calls:
        return True
    if str(msg.get("content") or "").strip():
        return False
    return None


def builtin_investigation_templates() -> List[Dict[str, Any]]:
    """Reusable tool sequences teams can run as 'My Investigation'."""
    return [
        {
            "id": "cpu_latency",
            "label": "CPU Latency Investigation",
            "steps": [
                "detect_anomalies",
                "investigate",
                "query_raw_metric",
                "correlate_events",
                "find_critical_path",
                "build_task_dependency_graph",
                "analyze_temporal_causality",
                "decompose_response_time",
                "rank_root_causes",
                "challenge_conclusion",
                "detect_priority_inversion",
                "generate_report",
            ],
        },
        {
            "id": "migration_thrash",
            "label": "Migration Thrash Investigation",
            "steps": [
                "detect_anomalies",
                "investigate",
                "correlate_events",
                "query_raw_metric",
                "what_if",
            ],
        },
        {
            "id": "regression",
            "label": "A/B Regression Investigation",
            "steps": [
                "compare_performance",
                "regression_explain",
                "validate_experiment",
                "generate_report",
            ],
        },
    ]


def match_historical_knowledge(
    task: str,
    *,
    current: Optional[dict] = None,
    history: Optional[dict] = None,
) -> Dict[str, Any]:
    """Compare a task's current metrics with a stored baseline profile."""
    name = str(task or "").strip()
    cur = current if isinstance(current, dict) else {}
    hist = history if isinstance(history, dict) else {}
    prev = hist.get(name) if isinstance(hist.get(name), dict) else (
        hist.get("tasks", {}).get(name) if isinstance(hist.get("tasks"), dict) else {}
    )
    if not isinstance(prev, dict):
        prev = {}
    flags = rate_flags_from_metrics(cur, prev)
    issue = str(prev.get("issue") or prev.get("previous_issue") or "")
    fix = str(prev.get("fix") or prev.get("known_fix") or "")
    build = str(prev.get("build") or prev.get("last_occurrence") or "")
    resembles = bool(issue) and bool(flags)
    return {
        "ok": True,
        "task": name,
        "previous_issue": issue,
        "known_fix": fix,
        "last_occurrence": build,
        "flags": flags,
        "typical": _metrics_from_mapping(prev),
        "current": _metrics_from_mapping(cur),
        "resembles_previous": resembles,
        "message": (
            f"This resembles the {issue} issue"
            + (f" seen in {build}" if build else "")
            if resembles else
            ("No historical match" if not prev else "Within historical range")
        ),
    }


def builtin_historical_catalog() -> List[Dict[str, Any]]:
    """Keyword catalog for common firmware investigation classes."""
    return [
        {
            "keywords": ("thrash", "migration", "bounc"),
            "issue": "Migration thrashing",
            "fix": "Pin the task / set core affinity",
            "build": "typical",
        },
        {
            "keywords": ("mutex", "contention", "blocking"),
            "issue": "Mutex contention",
            "fix": "Shorten the critical section or enable priority inheritance",
            "build": "typical",
        },
        {
            "keywords": ("inversion", "inherit"),
            "issue": "Priority inversion",
            "fix": "Priority inheritance or priority ceiling on the mutex",
            "build": "typical",
        },
        {
            "keywords": ("imbalance", "load balance"),
            "issue": "Load imbalance",
            "fix": "Rebalance placement or pin heavy tasks",
            "build": "typical",
        },
        {
            "keywords": ("deadline", "budget"),
            "issue": "Deadline miss",
            "fix": "Trim WCET or raise the budget / period",
            "build": "typical",
        },
    ]


def historical_knowledge_for_finding(
    finding: Optional[dict] = None,
    *,
    history: Optional[dict] = None,
    current: Optional[dict] = None,
    user_catalog: Optional[Sequence[dict]] = None,
) -> Dict[str, Any]:
    """Match user store, then baseline history, then the builtin catalog."""
    finding = finding if isinstance(finding, dict) else {}
    task = str(finding.get("task") or "")
    cur = current if isinstance(current, dict) else {}
    blob = f"{finding.get('title') or ''} {finding.get('text') or ''} {task}".lower()
    for item in parse_user_historical_knowledge(list(user_catalog or [])):
        item_task = str(item.get("task") or "").strip()
        keys = [str(k).lower() for k in (item.get("keywords") or []) if k]
        if (item_task and item_task.lower() == task.lower()) or (
            keys and any(k in blob for k in keys)
        ) or (item.get("issue") and str(item.get("issue")).lower() in blob):
            issue = str(item.get("issue") or "")
            fix = str(item.get("fix") or "")
            build = str(item.get("build") or "")
            typical = item.get("metrics") if isinstance(item.get("metrics"), dict) else {}
            flags = rate_flags_from_metrics(cur, typical)
            return {
                "ok": True,
                "task": task or item_task,
                "previous_issue": issue,
                "known_fix": fix,
                "last_occurrence": build,
                "flags": flags,
                "typical": typical,
                "current": _metrics_from_mapping(cur),
                "resembles_previous": True,
                "source": "user",
                "message": f"This resembles the {issue} issue"
                + (f" seen in {build}" if build else "")
                + (f" — known fix: {fix}" if fix else ""),
            }
    hit = match_historical_knowledge(task, current=cur, history=history)
    if hit.get("previous_issue") or hit.get("flags"):
        return hit
    for item in builtin_historical_catalog():
        if any(k in blob for k in (item.get("keywords") or ())):
            issue = str(item.get("issue") or "")
            fix = str(item.get("fix") or "")
            build = str(item.get("build") or "")
            return {
                "ok": True,
                "task": task,
                "previous_issue": issue,
                "known_fix": fix,
                "last_occurrence": build,
                "flags": [],
                "resembles_previous": True,
                "source": "catalog",
                "message": f"This resembles the {issue} issue"
                + (f" — known fix: {fix}" if fix else ""),
            }
    return hit


def build_investigation_case(
    investigate_ctx: Optional[dict] = None,
    *,
    question: str = "",
    trace: str = "",
    cursor_lo: Optional[float] = None,
    cursor_hi: Optional[float] = None,
    tools_run: Optional[Sequence[str]] = None,
    tools_executed: Optional[Sequence[str]] = None,
    mode: str = "diagnose",
    score_data: Optional[dict] = None,
    finding: Optional[dict] = None,
    hypotheses: Optional[Sequence[dict]] = None,
    alternatives: Optional[Sequence[dict]] = None,
    evidence: Optional[Sequence[dict]] = None,
    conclusion: str = "",
    confidence: str = "",
    checks: Optional[Sequence[dict]] = None,
    plan: Optional[dict] = None,
    **_extra: Any,
) -> Dict[str, Any]:
    """Assemble a Case from an ``investigate`` context (and optional extras)."""
    ctx = dict(investigate_ctx) if isinstance(investigate_ctx, dict) else {}
    if finding is not None:
        ctx["finding"] = finding
    if hypotheses is not None:
        ctx["hypotheses"] = list(hypotheses)
    if alternatives is not None:
        ctx["alternatives"] = list(alternatives)
    if evidence is not None:
        ctx["evidence"] = list(evidence)
    if checks is not None:
        ctx["checks"] = list(checks)
    if plan is not None:
        ctx["plan"] = plan
    if conclusion:
        ctx.setdefault("conclusion", conclusion)
    if score_data is None and isinstance(ctx.get("score_data"), dict):
        score_data = ctx.get("score_data")
    if score_data is None and isinstance(ctx.get("scoreData"), dict):
        score_data = ctx.get("scoreData")
    run = tools_run or tools_executed or ctx.get("tools_executed")
    finding_obj = ctx.get("finding") if isinstance(ctx.get("finding"), dict) else {}
    ev = list(
        evidence
        or finding_obj.get("evidence")
        or ctx.get("evidence")
        or []
    )
    hyps = enrich_hypotheses(
        ctx.get("hypotheses") or [],
        evidence=ev,
        alternatives=ctx.get("alternatives") or [],
    )
    graph = build_evidence_graph(
        finding_obj or None,
        evidence=ev,
        hypotheses=hyps,
        chain=ctx.get("root_cause_chain") or [],
    )
    score = score_data if isinstance(score_data, dict) else {}
    quality = compute_evidence_quality(
        score=score.get("score", ctx.get("evidence_score", 0)),
        breakdown=score.get("breakdown") or ctx.get("evidence_score_breakdown"),
        evidence=ev,
        alternatives=ctx.get("alternatives") or [],
        checks=ctx.get("checks") or [],
        evidence_chain=str(ctx.get("evidence_chain") or ""),
    )
    coverage = compute_evidence_coverage(evidence=ev)
    falsify = falsification_checks(finding_obj or None)
    if ev:
        falsify["supporting"] = [
            str(e.get("label") or "evidence")
            + (f" jump:{e.get('time')}" if e.get("time") is not None else "")
            for e in ev[:8] if isinstance(e, dict)
        ]
    tool_names: List[str] = []
    for t in (run or []):
        if isinstance(t, dict):
            n = str(t.get("name") or "").strip()
        else:
            n = str(t or "").strip()
        if n:
            tool_names.append(n)
    reasons = [
        {"tool": n, "reason": tool_call_reason(n, finding_obj or None)}
        for n in tool_names
    ]
    case = empty_investigation_case(
        question=question or str(ctx.get("message") or ctx.get("question") or ""),
        trace=trace,
        cursor_lo=cursor_lo,
        cursor_hi=cursor_hi,
        tasks=[str(finding_obj.get("task") or "")] if finding_obj.get("task") else [],
    )
    case.update({
        "suspected_findings": [finding_obj] if finding_obj else list(ctx.get("related_findings") or []),
        "hypotheses": hyps,
        "evidence": ev,
        "tools_executed": tool_names,
        "tool_reasons": reasons,
        "evidence_timeline": [
            {"time": e.get("time"), "label": e.get("label")}
            for e in ev if isinstance(e, dict) and e.get("time") is not None
        ],
        "evidence_graph": graph,
        "evidence_quality": quality,
        "evidence_coverage": coverage,
        "coverage": coverage,
        "falsification": falsify,
        "falsify": falsify,
        "graph_mermaid": graph.get("mermaid") or "",
        "confidence": confidence or quality.get("confidence_label") or "Medium",
        "confidence_history": record_confidence_step(
            [], tool_name="investigate",
            score=quality.get("score"), band=quality.get("band"),
            note="Initial investigation context",
        ),
        "conclusion": conclusion or str(finding_obj.get("title") or ""),
        "alternatives_rejected": [
            a for a in (ctx.get("alternatives") or [])
            if isinstance(a, dict) and str(a.get("status") or "").lower() == "rejected"
        ],
        "recommended_action": str(falsify.get("next_check") or ""),
        "mode": mode if mode in INVESTIGATION_MODES else "diagnose",
        "plan": ctx.get("plan"),
    })
    return case


def update_case_from_tool(
    case: Optional[dict],
    tool_name: str,
    result: Optional[dict] = None,
) -> Dict[str, Any]:
    """Fold a tool result into an existing Case (confidence evolution)."""
    out = dict(case or empty_investigation_case())
    name = str(tool_name or "").strip()
    tools = list(out.get("tools_executed") or [])
    if name and name not in tools:
        tools.append(name)
    out["tools_executed"] = tools
    reasons = list(out.get("tool_reasons") or [])
    finding = None
    suspected = out.get("suspected_findings") or []
    if suspected and isinstance(suspected[0], dict):
        finding = suspected[0]
    reasons.append({"tool": name, "reason": tool_call_reason(name, finding)})
    out["tool_reasons"] = reasons
    data = {}
    if isinstance(result, dict):
        data = result.get("data") if isinstance(result.get("data"), dict) else result
    ev = list(out.get("evidence") or [])
    for key in ("evidence", "events", "path"):
        for item in data.get(key) or []:
            if isinstance(item, dict):
                ev.append({
                    "label": str(item.get("label") or item.get("detail") or item.get("kind") or "evidence"),
                    "time": item.get("time"),
                })
    out["evidence"] = ev
    score = None
    if isinstance(data.get("evidence_score"), (int, float)):
        score = data.get("evidence_score")
    hist = record_confidence_step(
        out.get("confidence_history"),
        tool_name=name,
        score=score,
        note=str((result or {}).get("message") or "")[:160],
    )
    out["confidence_history"] = hist
    return out


# ---------------------------------------------------------------------------
# Benchmark / regression helpers (offline; no live model required)
# ---------------------------------------------------------------------------

BENCHMARK_METRIC_WEIGHTS: Dict[str, float] = {
    "finding": 0.20,
    "evidence": 0.20,
    "tool_use": 0.15,
    "root_cause": 0.20,
    "calibration": 0.10,
    "safety": 0.15,
}

_NEGATION_RE = re.compile(r"\b(not|no|never|isn't|is not|without|reject)\b")
_METRIC_SEP_RE = re.compile(r"[\s/_-]+")

# Official Statistics page titles plus wording a model may use instead of × / slashes.
AVAILABLE_STATISTICS_PAGES: Tuple[str, ...] = (
    "Timeline Anomalies",
    "Worst Events",
    "Period / Jitter",
    "Task Health",
    "Task × Core",
    "Waiter × Owner",
    "Response Time",
    "Critical Path",
    "Unified Jitter",
    "Recurring Patterns",
    "Preemption Matrix",
    "Mutex Blocking",
    "Core Utilization Over Time",
    "Switch Reason Breakdown",
    "Scheduling Load Over Time",
    "Activation Latency",
    "Ready-Gap (Starvation)",
    "Idle Analysis",
    "Queue Backlog / Semaphore Level",
)
STATS_UX_PAGE_ALIASES: Dict[str, Tuple[str, ...]] = {
    "timeline anomalies": ("timeline anomalies", "timeline anomaly"),
    "worst events": ("worst events", "worst event"),
    "period jitter": ("period jitter", "period / jitter", "period/jitter"),
    "task health": ("task health",),
    "task x core": ("task x core", "task-core"),
    "waiter x owner": ("waiter x owner", "waiter-owner"),
    "response time": ("response time", "response-time"),
    "critical path": ("critical path", "crit path"),
    "unified jitter": ("unified jitter",),
    "recurring patterns": ("recurring patterns", "recurring pattern"),
    "preemption matrix": ("preemption matrix",),
    "mutex blocking": ("mutex blocking", "mutex-blocking"),
    "core utilization over time": (
        "core utilization over time", "core utilisation over time",
    ),
    "switch reason breakdown": (
        "switch reason breakdown", "switch reason", "switch-reason",
    ),
    "scheduling load over time": (
        "scheduling load over time", "scheduling load",
    ),
    "activation latency": (
        "activation latency", "activation-latency", "release latency",
    ),
    "ready gap (starvation)": (
        "ready-gap (starvation)", "ready gap", "ready-gap", "starvation",
    ),
    "idle analysis": ("idle analysis",),
    "queue backlog semaphore level": (
        "queue backlog / semaphore level", "queue backlog", "semaphore level",
    ),
}


def _normalize_metric_text(text: str) -> str:
    return _METRIC_SEP_RE.sub(" ", str(text or "").lower().replace("×", "x")).strip()


def _metric_mentioned(blob: str, metric: str) -> bool:
    """True when *metric* (or a Statistics-page alias) appears in *blob*."""
    raw = str(blob or "").lower()
    want = str(metric or "").strip().lower()
    if want and want in raw:
        return True
    norm_blob = _normalize_metric_text(blob)
    norm_want = _normalize_metric_text(metric)
    if norm_want and norm_want in norm_blob:
        return True
    for key, needles in STATS_UX_PAGE_ALIASES.items():
        aliases = (key,) + tuple(needles)
        if norm_want not in {_normalize_metric_text(a) for a in aliases}:
            continue
        return any(
            _normalize_metric_text(n) in norm_blob or n in raw
            for n in needles
        )
    return False


def _blob_has_phrase(blob: str, phrase: str, *, allow_negation: bool = True) -> bool:
    text = str(blob or "").lower()
    needle = str(phrase or "").strip().lower()
    if not needle:
        return False
    idx = text.find(needle)
    if idx < 0:
        return False
    if allow_negation:
        window = text[max(0, idx - 20):idx]
        if _NEGATION_RE.search(window):
            return False
    return True


def score_adversarial_metrics(
    expected: Optional[dict] = None,
    *,
    actual_conclusion: str = "",
    tools: Optional[Sequence[str]] = None,
    validation: Optional[dict] = None,
) -> Dict[str, int]:
    """Rates (0–100, higher is worse) for trap / adversarial benchmark cases."""
    exp = expected if isinstance(expected, dict) else {}
    conc = str(actual_conclusion or "")
    traps = [str(x) for x in (exp.get("trap_phrases") or []) if str(x).strip()]
    false_confirmation = 100 if any(
        _blob_has_phrase(conc, p) for p in traps) else 0

    causal_hits = any(
        _blob_has_phrase(conc, p)
        for p in ("caused", "because of", "due to", "causal")
    )
    no_causal = bool(exp.get("no_causal")) or str(
        exp.get("root_cause_class") or "").lower() in ("no_causal", "coincidence")
    false_causal = 100 if no_causal and causal_hits else (
        false_confirmation if traps else 0)

    val = validation if isinstance(validation, dict) else {}
    claims = [c for c in (val.get("claims") or []) if isinstance(c, dict)]
    if claims:
        bad = sum(1 for c in claims if not c.get("ok"))
        unsupported = int(round(100.0 * bad / len(claims)))
    else:
        unsupported = 0

    tools_l = [str(t) for t in (tools or [])]
    required = [str(t) for t in (exp.get("required_tools") or []) if str(t)]
    high_conf = "confidence: high" in conc.lower() or conc.lower().endswith("high.")
    missing_required = bool(required) and not any(t in tools_l for t in required)
    premature = 100 if (
        (high_conf and (false_confirmation or missing_required or not tools_l))
        or missing_required
    ) else 0

    return {
        "false_causal_rate": int(false_causal),
        "false_confirmation_rate": int(false_confirmation),
        "unsupported_claim_rate": int(unsupported),
        "premature_conclusion_rate": int(premature),
    }


def score_benchmark_case(
    expected: dict,
    *,
    actual_finding_ids: Optional[Sequence[str]] = None,
    actual_tasks: Optional[Sequence[str]] = None,
    actual_tools: Optional[Sequence[str]] = None,
    actual_conclusion: str = "",
    validation: Optional[dict] = None,
    evidence_quality: Optional[dict] = None,
) -> Dict[str, Any]:
    """Weighted diagnostic score for one expected-facts case (0–100)."""
    exp = expected if isinstance(expected, dict) else {}
    want_findings = [str(x).lower() for x in (exp.get("finding_types") or [])]
    got_findings = [str(x).lower() for x in (actual_finding_ids or [])]
    finding_hits = sum(1 for w in want_findings if any(w in g for g in got_findings))
    finding_score = 100 if not want_findings else int(
        round(100.0 * finding_hits / len(want_findings)))

    want_tasks = [str(x).lower() for x in (exp.get("tasks") or [])]
    got_tasks = [str(x).lower() for x in (actual_tasks or [])]
    task_hits = sum(1 for w in want_tasks if any(w in g for g in got_tasks))
    evidence_score = 100 if not want_tasks else int(
        round(100.0 * task_hits / len(want_tasks)))
    ev = exp.get("evidence") if isinstance(exp.get("evidence"), dict) else {}
    want_metrics = [str(x).lower() for x in (ev.get("required_metrics") or [])]
    if want_metrics:
        blob = str(actual_conclusion or "")
        metric_hits = sum(1 for m in want_metrics if _metric_mentioned(blob, m))
        metric_score = int(round(100.0 * metric_hits / len(want_metrics)))
        evidence_score = (
            metric_score if not want_tasks
            else int(round((evidence_score + metric_score) / 2.0))
        )

    allowed = [str(x) for x in (exp.get("allowed_tools") or [])]
    got_tools = [str(x) for x in (actual_tools or [])]
    if allowed:
        tool_hits = sum(1 for t in got_tools if t in allowed)
        tool_score = int(round(100.0 * tool_hits / max(len(allowed), 1)))
        if got_tools and tool_hits == 0:
            tool_score = 0
        elif got_tools:
            tool_score = max(tool_score, int(round(100.0 * tool_hits / len(got_tools))))
    else:
        tool_score = 100 if got_tools else 50

    want_class = str(exp.get("root_cause_class") or "").lower()
    conc = str(actual_conclusion or "").lower()
    aliases = [str(x).lower() for x in (exp.get("root_cause_aliases") or []) if str(x).strip()]
    if not want_class and not aliases:
        root_score = 100
    elif (
        (want_class and (want_class in conc or any(w in conc for w in want_class.split())))
        or any(a in conc for a in aliases)
    ):
        root_score = 100
    else:
        root_score = 0
    adv = score_adversarial_metrics(
        exp,
        actual_conclusion=actual_conclusion,
        tools=actual_tools,
        validation=validation,
    )
    if adv.get("false_confirmation_rate"):
        root_score = 0

    band = str((evidence_quality or {}).get("band") or "")
    cal = 80
    if band in ("strong", "medium-high"):
        cal = 90
    elif band == "medium":
        cal = 75
    elif band in ("weak", "insufficient"):
        cal = 55

    val = validation if isinstance(validation, dict) else {}
    safety = 100 if val.get("ok", True) else max(
        0, 100 - 20 * int(val.get("unverified") or 1))
    if exp.get("forbidden", {}).get("invented_task_names") and any(
        c.get("kind") == "task" and not c.get("ok")
        for c in (val.get("claims") or [])
        if isinstance(c, dict)
    ):
        safety = min(safety, 40)

    parts = {
        "finding": finding_score,
        "evidence": evidence_score,
        "tool_use": tool_score,
        "root_cause": root_score,
        "calibration": cal,
        "safety": safety,
    }
    overall = int(round(sum(
        parts[k] * BENCHMARK_METRIC_WEIGHTS[k] for k in parts
    )))
    from .ai_planner import score_investigation_metrics
    extras = score_investigation_metrics(
        expected=exp,
        actual_conclusion=actual_conclusion,
        tools=actual_tools,
        evidence_quality=evidence_quality,
        catalog=None,
        passed=root_score >= 50 and finding_score >= 50,
        finding_score=finding_score,
    )
    extras.update(adv)
    return {
        "overall": max(0, min(100, overall)),
        "parts": parts,
        **extras,
    }


def format_benchmark_score(score: dict) -> str:
    overall = _safe_int((score or {}).get("overall"))
    filled = max(0, min(10, int(round(overall / 10))))
    bar = "█" * filled + "░" * (10 - filled)
    parts = (score or {}).get("parts") or {}
    lines = [f"Overall AI Diagnostic Score", f"{bar} {overall}", ""]
    for key in ("finding", "evidence", "tool_use", "root_cause", "calibration", "safety"):
        if key in parts:
            label = {
                "finding": "Finding",
                "evidence": "Evidence",
                "tool_use": "Tool use",
                "root_cause": "Root cause",
                "calibration": "Calibration",
                "safety": "Safety / grounding",
            }[key]
            lines.append(f"{label:20} {parts[key]}")
    extras = {
        "evidence_efficiency": "Evidence efficiency",
        "investigation_cost": "Investigation cost",
        "false_confidence": "False-confidence",
        "falsification_quality": "Falsification",
        "scope_accuracy": "Scope accuracy",
        "stop_efficiency": "Stop efficiency",
        "false_causal_rate": "False-causal rate",
        "false_confirmation_rate": "False-confirmation rate",
        "unsupported_claim_rate": "Unsupported-claim rate",
        "premature_conclusion_rate": "Premature-conclusion rate",
    }
    shown = False
    for key, label in extras.items():
        if key in (score or {}):
            if not shown:
                lines.append("")
                shown = True
            lines.append(f"{label:20} {(score or {}).get(key)}")
    return "\n".join(lines)


def _cases_from_json_obj(raw: Any) -> List[Dict[str, Any]]:
    if isinstance(raw, list):
        return [c for c in raw if isinstance(c, dict)]
    if isinstance(raw, dict) and isinstance(raw.get("cases"), list):
        return [c for c in raw["cases"] if isinstance(c, dict)]
    if isinstance(raw, dict) and raw.get("id"):
        return [raw]
    raise ValueError("benchmark dataset must be a JSON list, {cases: [...]}, or a case object")


def load_benchmark_dataset(path: str) -> List[Dict[str, Any]]:
    """Load ``tests/ai/dataset.json`` or a directory of JSON cases + traces."""
    src = Path(path)
    if src.is_dir():
        index = src / "dataset.json"
        if index.is_file():
            files = [index]
        else:
            files = sorted(
                p for p in src.glob("*.json")
                if p.name != "package.json"
            )
        if not files:
            raise FileNotFoundError(f"no dataset.json or *.json cases in {src}")
        cases: List[Dict[str, Any]] = []
        for f in files:
            with f.open("r", encoding="utf-8") as fh:
                cases.extend(_cases_from_json_obj(json.load(fh)))
        root = src
    elif src.is_file():
        with src.open("r", encoding="utf-8") as fh:
            cases = _cases_from_json_obj(json.load(fh))
        root = src.parent
    else:
        raise FileNotFoundError(f"benchmark dataset not found: {src}")
    seen: set = set()
    out: List[Dict[str, Any]] = []
    for case in cases:
        cid = str(case.get("id") or "")
        if cid and cid in seen:
            continue
        if cid:
            seen.add(cid)
        trace = str(case.get("trace") or "").strip()
        if trace:
            tp = Path(trace)
            case = dict(case)
            case["trace_path"] = str(tp if tp.is_absolute() else (root / tp).resolve())
        baseline = str(case.get("baseline_trace") or case.get("baseline") or "").strip()
        if baseline:
            bp = Path(baseline)
            case = dict(case)
            case["baseline_path"] = str(bp if bp.is_absolute() else (root / bp).resolve())
        out.append(case)
    return out


def evidence_quality_from_score(
    score: Any,
    breakdown: Optional[Sequence[dict]] = None,
    **kwargs: Any,
) -> Dict[str, Any]:
    """Alias used by the Evidence panel (same as ``compute_evidence_quality``)."""
    return compute_evidence_quality(
        score=score, breakdown=breakdown, **kwargs,
    )


def build_validation_catalog(
    *,
    findings_text: str = "",
    evidence: Optional[Sequence[dict]] = None,
    tasks: Optional[Sequence[str]] = None,
    metrics: Optional[Sequence[str]] = None,
    cursor_lo: Optional[float] = None,
    cursor_hi: Optional[float] = None,
    tool_times: Optional[Sequence[Any]] = None,
) -> Dict[str, Any]:
    """Known tasks / times / cursor window for ``validate_ai_response``."""
    known_tasks = [str(t) for t in (tasks or []) if t]
    for tok in _TASK_NAME_RE.findall(str(findings_text or "")):
        if tok not in known_tasks:
            known_tasks.append(tok)
    times: List[float] = []
    for e in evidence or []:
        if isinstance(e, dict) and e.get("time") is not None:
            try:
                times.append(float(e.get("time")))
            except (TypeError, ValueError):
                pass
    for t in tool_times or []:
        try:
            times.append(float(t))
        except (TypeError, ValueError):
            pass
    lo = cursor_lo
    hi = cursor_hi
    try:
        lo = float(lo) if lo is not None else None
    except (TypeError, ValueError):
        lo = None
    try:
        hi = float(hi) if hi is not None else None
    except (TypeError, ValueError):
        hi = None
    return {
        "tasks": known_tasks,
        "metrics": sorted(str(m) for m in (metrics or _KNOWN_METRICS)),
        "times": times,
        "cursor_lo": lo,
        "cursor_hi": hi,
    }


def infer_model_capability(
    model_name: str,
    *,
    tool_call_ok: Optional[bool] = None,
    chat_ok: bool = True,
    endpoint_is_local: bool = True,
    chat_text: str = "",
    tool_body: Any = None,
) -> Dict[str, Any]:
    cap = infer_model_capabilities(
        model_name, endpoint_is_local=endpoint_is_local,
    )
    cap["chat"] = "yes" if chat_ok else "no"
    if tool_call_ok is True:
        cap["tool_calling"] = "yes"
    elif tool_call_ok is False:
        cap["tool_calling"] = "partial"
    return merge_live_capability(
        cap, chat_text=chat_text, tool_body=tool_body, tool_ok=tool_call_ok,
    )


def format_capability_report(cap: Optional[Dict[str, Any]] = None) -> str:
    if not isinstance(cap, dict):
        return ""
    glyph = {"yes": "✓", "partial": "△", "no": "✗", "unknown": "?"}
    def g(v: Any) -> str:
        return glyph.get(str(v), str(v or ""))
    lines = [
        "Model capability",
        "",
        f"{g(cap.get('chat'))} Chat",
        f"{g(cap.get('structured_output'))} Structured output",
        f"{g(cap.get('tool_calling'))} Tool calling",
        f"{g(cap.get('multi_tool_chaining'))} Multi-tool chaining",
        f"{g(cap.get('long_context'))} Long context",
        f"{g(cap.get('complex_reasoning'))} Complex reasoning",
    ]
    rec = str(cap.get("recommended") or "").strip()
    if rec:
        lines.extend(["", f"Recommended: {rec}"])
    return "\n".join(lines)


def format_benchmark_report(run_id: str, rows: Sequence[Dict[str, Any]]) -> str:
    lines = [f"AI Benchmark #{run_id}", "", f"Cases: {len(rows)}", ""]
    for row in rows:
        name = str(row.get("id") or "?")
        score = row.get("overall")
        flag = "ERROR" if row.get("error") else ("PASS" if row.get("pass") else "FAIL")
        lines.append(f"  {name:24} {score!s:>3}  {flag}")
    if rows:
        avg = int(round(sum(int(r.get("overall") or 0) for r in rows) / len(rows)))
        lines.extend(["", f"Overall {avg}"])
    return "\n".join(lines) + "\n"


def _xml_text(el: Any) -> str:
    return (el.text or "").strip() if el is not None else ""


def _xml_child(parent: Any, *names: str) -> Any:
    if parent is None:
        return None
    for name in names:
        found = parent.find(name)
        if found is not None:
            return found
    return None


def resolve_benchmark_api_key(*, text: str = "", env: str = "") -> str:
    """Named env, else XML text. Shared env fallbacks only when no env= is set.

    A model with ``env="ANTHROPIC_API_KEY"`` must not inherit ``GEMINI_API_KEY``
    / ``OPENAI_API_KEY`` when its own variable is empty — that would keep
    optional suite models enabled on a Gemini-only host.
    """
    from .ai_assistant import normalize_api_key, read_ai_env_key, resolve_ai_api_key

    env_name = str(env or "").strip()
    if env_name:
        got = read_ai_env_key((env_name,))
        if got:
            return got
    got = normalize_api_key(text)
    if got:
        return got
    if env_name:
        return ""
    return resolve_ai_api_key("")


def _parse_benchmark_endpoint_xml(el: Any, defaults: Optional[dict] = None) -> Dict[str, Any]:
    from .ai_assistant import (
        normalize_ai_base_url,
        parse_ai_tls_verify,
    )

    out = dict(defaults or {})
    if not out.get("base_url"):
        out["base_url"] = ""
    if "tls_verify" not in out:
        out["tls_verify"] = True
    if "api_key" not in out:
        out["api_key"] = ""
    if "api_key_env" not in out:
        out["api_key_env"] = ""
    if "preset" not in out:
        out["preset"] = ""
    if "timeout_s" not in out:
        out["timeout_s"] = 0.0
    if el is None:
        return out
    url_el = _xml_child(el, "base-url", "base_url", "url")
    url = _xml_text(url_el) or str(el.get("base-url") or el.get("base_url") or "").strip()
    if url:
        out["base_url"] = normalize_ai_base_url(url)
    tls_raw = None
    tls_el = _xml_child(el, "tls-verify", "tls_verify")
    if tls_el is not None:
        tls_raw = _xml_text(tls_el) or tls_el.get("value")
    if el.get("tls-verify") is not None:
        tls_raw = el.get("tls-verify")
    elif el.get("tls_verify") is not None:
        tls_raw = el.get("tls_verify")
    if tls_raw is not None:
        out["tls_verify"] = parse_ai_tls_verify(tls_raw, default=True)
    if str(el.get("insecure") or "").strip().lower() in (
        "1", "true", "yes", "on",
    ):
        out["tls_verify"] = False
    key_el = _xml_child(el, "api-key", "api_key")
    env_name = ""
    key_text = ""
    if key_el is not None:
        env_name = str(key_el.get("env") or "").strip()
        key_text = _xml_text(key_el)
    env_name = env_name or str(el.get("api-key-env") or el.get("api_key_env") or "").strip()
    if env_name or key_text:
        out["api_key_env"] = env_name
        out["api_key"] = resolve_benchmark_api_key(text=key_text, env=env_name)
    preset_el = _xml_child(el, "preset")
    preset = _xml_text(preset_el) or str(el.get("preset") or "").strip()
    if preset:
        out["preset"] = preset
    to_el = _xml_child(el, "timeout-s", "timeout_s", "timeout")
    to_raw = _xml_text(to_el) or str(el.get("timeout-s") or el.get("timeout_s") or "").strip()
    if to_raw:
        try:
            out["timeout_s"] = float(to_raw)
        except ValueError:
            pass
    return out


def load_benchmark_suite_xml(path: Any) -> Dict[str, Any]:
    """Load a live ``ai-test`` suite from XML (models, URL, TLS, API key)."""
    import xml.etree.ElementTree as ET
    from .ai_assistant import parse_ai_tls_verify

    src = Path(path)
    if not src.is_file():
        raise FileNotFoundError(f"benchmark suite not found: {src}")
    try:
        root = ET.parse(str(src)).getroot()
    except ET.ParseError as exc:
        raise ValueError(f"invalid benchmark XML {src}: {exc}") from exc
    tag = str(root.tag or "").rsplit("}", 1)[-1].lower()
    if tag not in ("ai-benchmark", "benchmark", "suite"):
        raise ValueError(
            f"benchmark XML root must be <ai-benchmark> (got <{root.tag}>)"
        )
    xml_dir = src.parent
    cwd = Path.cwd()

    def _resolve(value: str) -> str:
        raw = str(value or "").strip()
        if not raw:
            return ""
        p = Path(raw)
        if p.is_absolute():
            return str(p)
        for base in (cwd, xml_dir):
            cand = (base / raw).resolve()
            if cand.exists():
                return str(cand)
        return str((cwd / raw).resolve())

    dataset_el = _xml_child(root, "dataset")
    output_el = _xml_child(root, "output")
    fail_el = _xml_child(root, "fail-under", "fail_under")
    fail_under = 0
    fail_raw = _xml_text(fail_el)
    if fail_raw:
        try:
            fail_under = int(fail_raw)
        except ValueError:
            fail_under = 0
    defaults = _parse_benchmark_endpoint_xml(_xml_child(root, "endpoint", "defaults"))
    models_el = _xml_child(root, "models")
    model_nodes = list((models_el if models_el is not None else root).findall("model"))
    models: List[Dict[str, Any]] = []
    for node in model_nodes:
        mid = str(node.get("id") or node.get("name") or _xml_text(node) or "").strip()
        if not mid:
            continue
        ep = _parse_benchmark_endpoint_xml(node, defaults)
        if not ep.get("base_url"):
            raise ValueError(f"model {mid!r} has no base-url (set <endpoint> or per-model)")
        models.append({
            "id": mid,
            "base_url": ep["base_url"],
            "tls_verify": bool(ep.get("tls_verify", True)),
            "api_key": str(ep.get("api_key") or ""),
            "api_key_env": str(ep.get("api_key_env") or ""),
            "preset": str(ep.get("preset") or ""),
            "timeout_s": float(ep.get("timeout_s") or 0.0),
            "optional": parse_ai_tls_verify(
                node.get("optional") or node.get("opt"), default=False),
        })
    if not models:
        raise ValueError("benchmark XML has no <model id=...> entries")
    dataset = _xml_text(dataset_el) or "tests/ai"
    return {
        "path": str(src.resolve()),
        "dataset": _resolve(dataset),
        "dataset_raw": dataset,
        "fail_under": fail_under,
        "output": _xml_text(output_el),
        "defaults": defaults,
        "models": models,
    }


def parse_live_benchmark_models(models_raw: str) -> List[str]:
    """Comma-separated model ids from ``--models`` (filters the suite XML)."""
    return [m.strip() for m in str(models_raw or "").split(",") if m.strip()]


def select_benchmark_cases(
    cases: Sequence[Dict[str, Any]],
    case_ids_raw: str = "",
) -> List[Dict[str, Any]]:
    """Dataset cases, optionally filtered by ``--only-cases`` ids.

    With no filter, every case is scored (unchanged order). Unknown ids raise
    ``ValueError`` (mirrors :func:`select_benchmark_suite_models`).
    """
    want = parse_live_benchmark_models(case_ids_raw)
    if not want:
        return list(cases)
    by_id = {str(c.get("id") or ""): c for c in cases}
    out: List[Dict[str, Any]] = []
    missing: List[str] = []
    for cid in want:
        if cid in by_id:
            out.append(by_id[cid])
        else:
            missing.append(cid)
    if missing:
        known = ", ".join(by_id) or "(none)"
        raise ValueError(
            f"case id(s) not in dataset: {', '.join(missing)} (have {known})"
        )
    return out


def select_benchmark_suite_models(
    suite: dict,
    models_raw: str = "",
) -> List[Dict[str, Any]]:
    """Return suite model dicts, optionally filtered by ``--models`` ids.

    With no ``--models`` filter, optional remote models without an API key
    are skipped (``optional="true"`` in the suite XML).
    """
    from .ai_assistant import is_local_ai_host

    models = list((suite or {}).get("models") or [])
    want = parse_live_benchmark_models(models_raw)
    if not want:
        out: List[Dict[str, Any]] = []
        for m in models:
            if m.get("optional"):
                url = str(m.get("base_url") or "")
                key = str(m.get("api_key") or "")
                if not is_local_ai_host(url) and not key:
                    continue
            out.append(m)
        return out
    by_id = {str(m.get("id") or ""): m for m in models}
    out: List[Dict[str, Any]] = []
    missing: List[str] = []
    for mid in want:
        if mid in by_id:
            out.append(by_id[mid])
        else:
            missing.append(mid)
    if missing:
        known = ", ".join(by_id) or "(none)"
        raise ValueError(
            f"model id(s) not in suite XML: {', '.join(missing)} (have {known})"
        )
    return out


def benchmark_model_category(model: str) -> str:
    low = str(model or "").lower()
    if "gemini" in low:
        if "flash-lite" in low or "flash_lite" in low:
            return "Cloud / fast"
        if "pro" in low:
            return "Cloud / frontier"
        return "Cloud"
    if "gpt-" in low or "gpt4" in low:
        return "Cloud"
    if "claude" in low:
        return "Cloud"
    if "kimi" in low or "moonshot" in low:
        return "Cloud"
    if "phi4" in low or "phi-4" in low:
        return "Local / historical baseline"
    if "35b" in low or "a3b" in low:
        return "Local / experimental"
    if any(tok in low for tok in ("27b", "26b", "14b", "32b")):
        return "Local / high-quality"
    return "Local / practical"


def benchmark_prompt_context(case: dict) -> str:
    """Catalog-only Findings text for a live case (does not leak expected labels)."""
    catalog = case.get("catalog") if isinstance(case.get("catalog"), dict) else {}
    tasks = ", ".join(str(t) for t in (catalog.get("tasks") or []) if str(t).strip())
    times = catalog.get("times") or []
    jumps = ", ".join(f"jump:{t}" for t in times)
    lo, hi = catalog.get("cursor_lo"), catalog.get("cursor_hi")
    lines = [
        "Benchmark investigation. Use only this catalog.",
        f"Trace: {case.get('trace') or ''}",
        f"Known tasks: {tasks or '(none)'}",
    ]
    if lo is not None and hi is not None:
        lines.append(f"Cursor region window: jump:{lo} … jump:{hi}")
    if jumps:
        lines.append(f"Evidence times: {jumps}")
    lines.append(
        "Call an allowed investigation tool if needed. "
        "Cite jump:TIME and Task[id] from the catalog. "
        "State confidence (High / Medium / Low). "
        "Do not invent tasks, metrics, or timestamps."
    )
    return "\n".join(lines)


def score_benchmark_response(
    case: dict,
    *,
    response: str,
    tools: Optional[Sequence[str]] = None,
    fail_under: int = 0,
    elapsed_s: Optional[float] = None,
    prompt_tokens: Optional[int] = None,
    completion_tokens: Optional[int] = None,
    total_tokens: Optional[int] = None,
) -> Dict[str, Any]:
    """Score one case from a model (or fixture) reply."""
    expected = case.get("expected") if isinstance(case.get("expected"), dict) else case
    catalog = case.get("catalog") if isinstance(case.get("catalog"), dict) else {}
    report = validate_ai_response(
        response,
        known_tasks=catalog.get("tasks"),
        known_times=catalog.get("times"),
        cursor_lo=catalog.get("cursor_lo"),
        cursor_hi=catalog.get("cursor_hi"),
    )
    blob = str(response or "").lower()
    got_findings = [
        ft for ft in (expected.get("finding_types") or [])
        if str(ft).lower() in blob
    ]
    scored = score_benchmark_case(
        expected,
        actual_finding_ids=got_findings,
        actual_tasks=[
            str(c.get("value")) for c in (report.get("claims") or [])
            if isinstance(c, dict) and c.get("kind") == "task"
        ],
        actual_tools=list(tools or []),
        actual_conclusion=response,
        validation=report,
    )
    scored["id"] = case.get("id") or expected.get("id")
    floor = int(expected.get("pass_under") or fail_under or 70)
    scored["pass"] = int(scored.get("overall") or 0) >= floor and bool(
        report.get("ok", True) or not (expected.get("forbidden") or {})
    )
    if expected.get("forbidden", {}).get("invented_task_names") and not report.get("ok"):
        invented = any(
            c.get("kind") == "task" and not c.get("ok")
            for c in (report.get("claims") or [])
            if isinstance(c, dict)
        )
        if invented:
            scored["pass"] = False
    if expected.get("forbidden", {}).get("out_of_scope_timestamps"):
        oos = any(
            c.get("kind") == "jump" and not c.get("ok")
            for c in (report.get("claims") or [])
            if isinstance(c, dict)
        )
        if oos:
            scored["pass"] = False
    if fail_under and int(scored.get("overall") or 0) < int(fail_under):
        scored["pass"] = False
    scored["validation"] = report
    if elapsed_s is not None:
        scored["elapsed_s"] = round(float(elapsed_s), 2)
    if prompt_tokens is not None:
        scored["prompt_tokens"] = max(0, _safe_int(prompt_tokens))
    if completion_tokens is not None:
        scored["completion_tokens"] = max(0, _safe_int(completion_tokens))
    if total_tokens is not None:
        scored["total_tokens"] = max(0, _safe_int(total_tokens))
    scored["tools"] = list(tools or [])
    return scored


def run_offline_benchmark(
    dataset_path: Any,
    *,
    fail_under: int = 0,
    case_ids: str = "",
) -> Dict[str, Any]:
    """Score fixture responses in a dataset (no live model calls).

    *case_ids*: optional comma-separated ``--only-cases`` filter (see
    :func:`select_benchmark_cases`); empty scores every case.
    """
    from datetime import datetime, timezone
    cases = select_benchmark_cases(load_benchmark_dataset(str(dataset_path)), case_ids)
    rows: List[Dict[str, Any]] = []
    for case in cases:
        actual = case.get("actual") if isinstance(case.get("actual"), dict) else {}
        response = str(actual.get("response") or case.get("response") or "")
        tools = list(actual.get("tools") or case.get("tools") or [])
        rows.append(score_benchmark_response(
            case, response=response, tools=tools, fail_under=fail_under,
        ))
    run_id = datetime.now(timezone.utc).strftime("%Y-%m-%d-%H%M%S")
    failed = [r for r in rows if not r.get("pass")]
    return {
        "run_id": run_id,
        "mode": "offline",
        "rows": rows,
        "failed": failed,
        "report": format_benchmark_report(run_id, rows),
        "ok": not failed,
    }


def parse_benchmark_context_modes(raw: str = "") -> List[str]:
    """Parse ``--context-mode`` / ``--compare-context`` for live ai-test."""
    text = str(raw or "").strip().lower()
    if text in ("", "all", "compare", "compare-context", "three"):
        return list(AI_CONTEXT_MODES)
    if text in ("default", "full", "full evidence"):
        return [AI_CONTEXT_MODE_FULL]
    out: List[str] = []
    seen = set()
    for part in re.split(r"[\s,]+", text):
        key = normalize_ai_context_mode(part)
        if key not in seen:
            seen.add(key)
            out.append(key)
    return out or [DEFAULT_AI_CONTEXT_MODE]


def run_live_benchmark(
    dataset_path: Any,
    models: Sequence[str],
    *,
    complete: Callable[..., Dict[str, Any]],
    fail_under: int = 0,
    context_modes: Optional[Sequence[str]] = None,
    case_ids: str = "",
) -> Dict[str, Any]:
    """Score live model replies. *complete(query, findings_text, model, case, context_mode=...)*.

    *case_ids*: optional comma-separated ``--only-cases`` filter (see
    :func:`select_benchmark_cases`); empty scores every case.
    """
    from datetime import datetime, timezone
    ids = [str(m).strip() for m in (models or []) if str(m).strip()]
    if not ids:
        raise ValueError("live benchmark needs at least one model id")
    modes = [
        normalize_ai_context_mode(m)
        for m in (context_modes or [AI_CONTEXT_MODE_FULL])
    ]
    seen_modes = set()
    mode_list: List[str] = []
    for m in modes:
        if m not in seen_modes:
            seen_modes.add(m)
            mode_list.append(m)
    cases = select_benchmark_cases(load_benchmark_dataset(str(dataset_path)), case_ids)
    run_id = datetime.now(timezone.utc).strftime("%Y-%m-%d-%H%M%S")
    per_model: List[Dict[str, Any]] = []
    for model in ids:
        for ctx_mode in mode_list:
            rows: List[Dict[str, Any]] = []
            error = ""
            for case in cases:
                query = str(case.get("question") or "").strip() or "Investigate the main problem."
                findings = benchmark_prompt_context(case)
                try:
                    turn = complete(
                        query, findings, model, case, context_mode=ctx_mode) or {}
                except TypeError:
                    turn = complete(query, findings, model, case) or {}
                except Exception as exc:
                    error = str(exc)
                    turn = {
                        "content": "",
                        "tool_calls": [],
                        "elapsed_s": 0,
                        "usage": {},
                        "error": error,
                    }
                if not isinstance(turn, dict):
                    turn = {"content": str(turn or "")}
                content = str(turn.get("content") or "")
                raw_calls = turn.get("tool_calls") or []
                names: List[str] = []
                for c in raw_calls:
                    if isinstance(c, dict):
                        name = str(c.get("name") or "")
                        if name:
                            names.append(name)
                    elif c:
                        names.append(str(c))
                usage = turn.get("usage") if isinstance(turn.get("usage"), dict) else {}
                row = score_benchmark_response(
                    case,
                    response=content,
                    tools=names,
                    fail_under=fail_under,
                    elapsed_s=turn.get("elapsed_s"),
                    prompt_tokens=usage.get("prompt_tokens"),
                    completion_tokens=usage.get("completion_tokens"),
                    total_tokens=usage.get("total_tokens"),
                )
                if turn.get("error"):
                    row["error"] = str(turn.get("error"))
                    row["pass"] = False
                rows.append(row)
            failed = [r for r in rows if not r.get("pass")]
            label = ai_context_mode_label(ctx_mode)
            block_id = model if len(mode_list) == 1 else f"{model} ({label})"
            per_model.append({
                "model": model,
                "context_mode": ctx_mode,
                "context_label": label,
                "block_id": block_id,
                "category": benchmark_model_category(model),
                "run_id": run_id,
                "rows": rows,
                "failed": failed,
                "report": format_benchmark_report(f"{run_id}-{block_id}", rows),
                "ok": not failed and not error,
                "error": error,
            })
    return {
        "run_id": run_id,
        "mode": "live",
        "context_modes": mode_list,
        "models": per_model,
        "ok": all(m.get("ok") for m in per_model),
        "report": "".join(m["report"] for m in per_model),
    }


def format_benchmark_markdown(
    *,
    offline: Optional[dict] = None,
    live: Optional[dict] = None,
    dataset: str = "tests/ai",
) -> str:
    """Markdown report for AI_BENCHMARK.md (offline scorer + optional live models)."""
    from datetime import datetime, timezone
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    lines = [
        "# AI Benchmark results",
        "",
        f"Generated: {stamp}",
        f"Dataset: `{dataset}`",
        "",
        "Live `--config` suite XML scores a real endpoint. Offline rows score the canned "
        "`response` fields in `dataset.json` and gate the scorer, not a model.",
        "",
    ]
    part_keys = (
        "finding", "evidence", "tool_use", "root_cause", "calibration", "safety",
    )

    def _row_stats(rows: Sequence[dict]) -> Dict[str, Any]:
        seq = list(rows or [])
        n = len(seq)
        avg_overall = int(round(sum(int(r.get("overall") or 0) for r in seq) / n)) if n else 0
        passed = sum(1 for r in seq if r.get("pass"))
        lat = [
            float(r.get("elapsed_s") or 0)
            for r in seq if r.get("elapsed_s") is not None
        ]
        mean_lat = sum(lat) / len(lat) if lat else None
        prompt = sum(int(r.get("prompt_tokens") or 0) for r in seq)
        completion = sum(int(r.get("completion_tokens") or 0) for r in seq)
        total = sum(int(r.get("total_tokens") or 0) for r in seq)
        return {
            "n": n,
            "avg_overall": avg_overall,
            "passed": passed,
            "mean_lat": mean_lat,
            "prompt_tokens": prompt,
            "completion_tokens": completion,
            "total_tokens": total or (prompt + completion),
        }

    def _table(rows: Sequence[dict]) -> List[str]:
        out = [
            "| Case | Overall | Finding | Evidence | Tool use | Root cause | Calibration | Safety | Result |",
            "|---|---:|---:|---:|---:|---:|---:|---:|---|",
        ]
        for row in rows:
            parts = row.get("parts") or {}
            flag = "ERROR" if row.get("error") else (
                "PASS" if row.get("pass") else "FAIL"
            )
            cells = [
                str(row.get("id") or "?"),
                str(row.get("overall") or 0),
            ]
            cells.extend(str(parts.get(k, "")) for k in part_keys)
            cells.append(flag)
            out.append("| " + " | ".join(cells) + " |")
        if rows:
            avg = int(round(sum(int(r.get("overall") or 0) for r in rows) / len(rows)))
            out.extend(["", f"**Overall {avg}**"])
        return out

    if offline:
        lines.extend([
            "## Offline fixture scorer",
            "",
            f"Run `{offline.get('run_id') or ''}` — no live model.",
            "",
        ])
        lines.extend(_table(offline.get("rows") or []))
        lines.append("")
    if live:
        blocks = list(live.get("models") or [])
        mode_list = list(live.get("context_modes") or [])
        multi_ctx = len(mode_list) > 1
        if blocks:
            header = (
                "| Model | Context | Category | Overall | Pass | Total tok | Mean latency |"
                if multi_ctx else
                "| Model | Category | Overall | Pass | Total tok | Mean latency |"
            )
            sep = (
                "|---|---|---|---:|---:|---:|---:|"
                if multi_ctx else
                "|---|---|---:|---:|---:|---:|"
            )
            lines.extend([
                "## Comparison",
                "",
                header,
                sep,
            ])
            for block in blocks:
                stats = _row_stats(block.get("rows") or [])
                mean_lat = f"{stats['mean_lat']:.1f}s" if stats["mean_lat"] is not None else "—"
                tok = stats["total_tokens"] or "—"
                cells = [f"`{block.get('model') or '?'}`"]
                if multi_ctx:
                    cells.append(str(block.get("context_label") or ai_context_mode_label(
                        block.get("context_mode"))))
                cells.extend([
                    str(block.get("category") or ""),
                    str(stats["avg_overall"]),
                    f"{stats['passed']}/{stats['n']}",
                    str(tok),
                    mean_lat,
                ])
                lines.append("| " + " | ".join(cells) + " |")
            if multi_ctx:
                by_model: Dict[str, List[dict]] = {}
                for block in blocks:
                    by_model.setdefault(str(block.get("model") or "?"), []).append(block)
                lines.extend([
                    "",
                    "## Context mode comparison",
                    "",
                    "Same model and dataset; Compact / Balanced / Full evidence packing.",
                    "",
                ])
                for model, group in by_model.items():
                    lines.extend([f"### `{model}`", ""])
                    lines.extend([
                        "| Context | Overall | Pass | Prompt tok | Completion tok | "
                        "Total tok | Mean latency |",
                        "|---|---:|---:|---:|---:|---:|---:|",
                    ])
                    for block in sorted(
                        group,
                        key=lambda b: AI_CONTEXT_MODES.index(
                            normalize_ai_context_mode(b.get("context_mode"))
                        ) if normalize_ai_context_mode(
                            b.get("context_mode")) in AI_CONTEXT_MODES else 99,
                    ):
                        stats = _row_stats(block.get("rows") or [])
                        mean_lat = (
                            f"{stats['mean_lat']:.1f}s"
                            if stats["mean_lat"] is not None else "—"
                        )
                        lines.append(
                            "| "
                            + " | ".join([
                                str(block.get("context_label") or "?"),
                                str(stats["avg_overall"]),
                                f"{stats['passed']}/{stats['n']}",
                                str(stats["prompt_tokens"] or "—"),
                                str(stats["completion_tokens"] or "—"),
                                str(stats["total_tokens"] or "—"),
                                mean_lat,
                            ])
                            + " |"
                        )
                    lines.append("")
            lines.extend([
                "",
                "| Model | Finding | Evidence | Tool use | Root cause | Calibration | Safety |",
                "|---|---:|---:|---:|---:|---:|---:|",
            ])
            for block in blocks:
                rows = list(block.get("rows") or [])
                n = max(len(rows), 1)
                parts_avg = {}
                for key in part_keys:
                    parts_avg[key] = int(round(sum(
                        int((r.get("parts") or {}).get(key) or 0) for r in rows
                    ) / n)) if rows else 0
                label = str(block.get("block_id") or block.get("model") or "?")
                cells = [f"`{label}`"]
                cells.extend(str(parts_avg[k]) for k in part_keys)
                lines.append("| " + " | ".join(cells) + " |")
            lines.append("")
        lines.extend(["## Live models", ""])
        for block in live.get("models") or []:
            model = str(block.get("model") or "")
            cat = str(block.get("category") or benchmark_model_category(model))
            ctx = str(block.get("context_label") or "").strip()
            title = f"`{model}`"
            if ctx:
                title = f"`{model}` — {ctx}"
            lines.extend([
                f"### {title}",
                "",
                f"{cat}. Run `{block.get('run_id') or live.get('run_id') or ''}`.",
                "",
            ])
            if block.get("error"):
                lines.extend([f"Error: {block['error']}", ""])
            lines.extend(_table(block.get("rows") or []))
            row_errors = [
                (str(r.get("id") or "?"), str(r.get("error") or "").strip())
                for r in (block.get("rows") or [])
                if r.get("error")
            ]
            if row_errors:
                first = row_errors[0][1]
                n_err = len(row_errors)
                snippet = first.split("\n", 1)[0][:240]
                lines.extend([
                    "",
                    f"{n_err}/{len(block.get('rows') or [])} cases returned an API error "
                    f"(first: {snippet}).",
                ])
            lat = [
                float(r.get("elapsed_s") or 0)
                for r in (block.get("rows") or [])
                if r.get("elapsed_s") is not None
            ]
            if lat:
                avg_s = sum(lat) / len(lat)
                lines.extend(["", f"Mean latency: **{avg_s:.1f}s** / case."])
            tok = _row_stats(block.get("rows") or [])
            if tok["total_tokens"]:
                lines.extend([
                    "",
                    f"Tokens: **{tok['prompt_tokens']}** prompt + "
                    f"**{tok['completion_tokens']}** completion = "
                    f"**{tok['total_tokens']}** total.",
                ])
            lines.append("")
    if not offline and not live:
        lines.append("_No runs recorded._")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


_BENCH_CASE_ROW_KEYS = (
    "finding", "evidence", "tool_use", "root_cause", "calibration", "safety",
)
_BENCH_LIVE_HEADER_RE = re.compile(r"^###\s+`([^`]+)`(?:\s+—\s+(.+))?\s*$")
_BENCH_RUN_LINE_RE = re.compile(r"Run `([^`]*)`")
_BENCH_ERROR_SUMMARY_RE = re.compile(
    r"^\d+/\d+ cases returned an API error \(first: (.*)\)\.$"
)
_BENCH_MEAN_LAT_RE = re.compile(r"Mean latency: \*\*([\d.]+)s\*\* / case\.")
_BENCH_TOKENS_RE = re.compile(
    r"Tokens: \*\*(\d+)\*\* prompt \+ \*\*(\d+)\*\* completion = \*\*(\d+)\*\* total\."
)
_BENCH_STALE_ERROR_TEXT = (
    "carried over from a previous AI_BENCHMARK.md (original error text unavailable)"
)


def _split_benchmark_md_row(line: str) -> List[str]:
    s = line.strip()
    if s.startswith("|"):
        s = s[1:]
    if s.endswith("|"):
        s = s[:-1]
    return [c.strip() for c in s.split("|")]


def _parse_benchmark_case_table(
    lines: Sequence[str], start: int,
) -> Tuple[List[Dict[str, Any]], int]:
    """Parse a ``| Case | Overall | ... | Result |`` table (see ``_table`` in
    :func:`format_benchmark_markdown`) starting at ``lines[start]``.

    Returns ``(rows, index_after_table)``; ``rows`` round-trip enough of the
    prior report (overall, parts, pass/fail/error) for
    :func:`merge_benchmark_report` to recompute an unchanged block's stats.
    """
    if start >= len(lines) or "| Case |" not in lines[start]:
        return [], start
    i = start + 2
    rows: List[Dict[str, Any]] = []
    while i < len(lines) and lines[i].strip().startswith("|"):
        cells = _split_benchmark_md_row(lines[i])
        if len(cells) < 9:
            break
        case_id = cells[0]
        flag = cells[8].strip().upper()
        rows.append({
            "id": case_id,
            "overall": _safe_int(cells[1]),
            "parts": {
                key: _safe_int(cells[2 + idx])
                for idx, key in enumerate(_BENCH_CASE_ROW_KEYS)
            },
            "pass": flag == "PASS",
            "error": _BENCH_STALE_ERROR_TEXT if flag == "ERROR" else "",
        })
        i += 1
    return rows, i


def _parse_benchmark_offline_section(
    lines: Sequence[str], start: int, end: int,
) -> Optional[Dict[str, Any]]:
    run_id = ""
    for i in range(start, end):
        m = _BENCH_RUN_LINE_RE.search(lines[i])
        if m:
            run_id = m.group(1)
        if lines[i].strip().startswith("| Case |"):
            rows, _ = _parse_benchmark_case_table(lines, i)
            return {"run_id": run_id, "rows": rows} if rows else None
    return None


def _parse_benchmark_live_blocks(
    lines: Sequence[str], start: int, end: int,
) -> List[Dict[str, Any]]:
    blocks: List[Dict[str, Any]] = []
    i = start
    while i < end:
        m = _BENCH_LIVE_HEADER_RE.match(lines[i].strip())
        if not m:
            i += 1
            continue
        model = m.group(1)
        label = (m.group(2) or "").strip()
        ctx_mode = normalize_ai_context_mode(label) if label else AI_CONTEXT_MODE_FULL
        j = i + 1
        run_id = ""
        block_error = ""
        while j < end and not lines[j].strip().startswith(("| Case |", "### ", "## ")):
            line = lines[j].strip()
            rm = _BENCH_RUN_LINE_RE.search(line)
            if rm:
                run_id = rm.group(1)
            elif line.startswith("Error: "):
                block_error = line[len("Error: "):]
            j += 1
        rows: List[Dict[str, Any]] = []
        if j < end and lines[j].strip().startswith("| Case |"):
            rows, j = _parse_benchmark_case_table(lines, j)
        mean_lat: Optional[float] = None
        prompt_tok = completion_tok = total_tok = None
        error_msg = ""
        while j < end and not lines[j].strip().startswith(("### ", "## ")):
            line = lines[j].strip()
            em = _BENCH_ERROR_SUMMARY_RE.match(line)
            if em:
                error_msg = em.group(1)
            lm = _BENCH_MEAN_LAT_RE.search(line)
            if lm:
                mean_lat = float(lm.group(1))
            tm = _BENCH_TOKENS_RE.search(line)
            if tm:
                prompt_tok, completion_tok, total_tok = (
                    int(tm.group(1)), int(tm.group(2)), int(tm.group(3)),
                )
            j += 1
        if rows:
            if mean_lat is not None:
                for r in rows:
                    r["elapsed_s"] = mean_lat
            if prompt_tok is not None:
                rows[0]["prompt_tokens"] = prompt_tok
                rows[0]["completion_tokens"] = completion_tok
                rows[0]["total_tokens"] = total_tok
            if error_msg:
                for r in rows:
                    if r.get("error"):
                        r["error"] = error_msg
        blocks.append({
            "model": model,
            "context_mode": ctx_mode,
            "context_label": ai_context_mode_label(ctx_mode),
            "block_id": model,
            "category": benchmark_model_category(model),
            "run_id": run_id,
            "rows": rows,
            "failed": [r for r in rows if not r.get("pass")],
            "ok": all(r.get("pass") for r in rows) if rows else True,
            "error": block_error,
        })
        i = j
    return blocks


def parse_benchmark_markdown(text: str) -> Dict[str, Any]:
    """Recover ``offline``/``live`` structures from a previously written
    AI_BENCHMARK.md so :func:`merge_benchmark_report` can update only the
    models/cases that were actually rerun. Returns ``{}`` for text that
    doesn't look like a benchmark report (e.g. an empty or hand-edited file).
    """
    lines = (text or "").splitlines()
    headings = [
        (i, ln.strip()[3:].strip())
        for i, ln in enumerate(lines) if ln.strip().startswith("## ")
    ]
    if not headings:
        return {}
    bounds: Dict[str, Tuple[int, int]] = {}
    for k, (idx, title) in enumerate(headings):
        end = headings[k + 1][0] if k + 1 < len(headings) else len(lines)
        bounds.setdefault(title, (idx, end))
    result: Dict[str, Any] = {}
    if "Offline fixture scorer" in bounds:
        start, end = bounds["Offline fixture scorer"]
        offline = _parse_benchmark_offline_section(lines, start, end)
        if offline:
            result["offline"] = offline
    if "Live models" in bounds:
        start, end = bounds["Live models"]
        blocks = _parse_benchmark_live_blocks(lines, start, end)
        if blocks:
            modes: List[str] = []
            seen = set()
            for b in blocks:
                cm = b["context_mode"]
                if cm not in seen:
                    seen.add(cm)
                    modes.append(cm)
            single_mode = len(modes) <= 1
            for b in blocks:
                b["block_id"] = (
                    b["model"] if single_mode else f"{b['model']} ({b['context_label']})"
                )
            result["live"] = {"models": blocks, "context_modes": modes}
    return result


def merge_benchmark_report(
    existing_text: str,
    *,
    offline: Optional[dict] = None,
    live: Optional[dict] = None,
) -> Tuple[Optional[dict], Optional[dict]]:
    """Combine a freshly scored run with whatever ``existing_text`` (a prior
    AI_BENCHMARK.md) already recorded, so e.g. rerunning just
    ``gemini-3.7-flash`` in Full evidence updates that one model/context
    block — and the offline cases actually rescored — without dropping every
    other model, context mode, or case from the report.

    Returns ``(merged_offline, merged_live)`` ready for
    :func:`format_benchmark_markdown`. Falls back to ``(offline, live)``
    unchanged (a plain overwrite) when ``existing_text`` doesn't parse as a
    benchmark report.
    """
    prior = parse_benchmark_markdown(existing_text or "")
    merged_offline = offline
    prior_offline = prior.get("offline")
    if prior_offline:
        old_rows = list(prior_offline.get("rows") or [])
        new_rows = list((offline or {}).get("rows") or [])
        by_id = {r["id"]: r for r in old_rows}
        order = [r["id"] for r in old_rows]
        for r in new_rows:
            if r["id"] not in by_id:
                order.append(r["id"])
            by_id[r["id"]] = r
        merged_rows = [by_id[cid] for cid in order]
        run_id = (offline or {}).get("run_id") or prior_offline.get("run_id") or ""
        merged_offline = {**(offline or {}), "run_id": run_id, "rows": merged_rows}
    merged_live = live
    prior_live = prior.get("live")
    if prior_live:
        old_blocks = list(prior_live.get("models") or [])
        new_blocks = list((live or {}).get("models") or [])
        by_key = {(b.get("model"), b.get("context_mode")): b for b in old_blocks}
        order_keys = list(by_key.keys())
        for b in new_blocks:
            key = (b.get("model"), b.get("context_mode"))
            if key not in by_key:
                order_keys.append(key)
            by_key[key] = b
        merged_blocks = [by_key[k] for k in order_keys]
        modes: List[str] = []
        seen_modes = set()
        for b in merged_blocks:
            cm = b.get("context_mode")
            if cm not in seen_modes:
                seen_modes.add(cm)
                modes.append(cm)
        modes.sort(
            key=lambda m: AI_CONTEXT_MODES.index(m) if m in AI_CONTEXT_MODES else 99
        )
        single_mode = len(modes) <= 1
        for b in merged_blocks:
            label = b.get("context_label") or ai_context_mode_label(b.get("context_mode"))
            b["block_id"] = b.get("model") if single_mode else f"{b.get('model')} ({label})"
        run_id = (live or {}).get("run_id") or prior_live.get("run_id") or ""
        merged_live = {
            **(live or {}),
            "run_id": run_id,
            "models": merged_blocks,
            "context_modes": modes,
            "ok": all(b.get("ok", True) for b in merged_blocks),
        }
    return merged_offline, merged_live
