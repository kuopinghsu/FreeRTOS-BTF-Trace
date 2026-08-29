"""Viewer tool-calling schema for the AI Assistant (Desktop + Web).

OpenAI / Ollama / Gemini OpenAI-compat ``tools`` definitions. Keep in sync
with ``web/src/utils/aiTools.js``.
"""
from __future__ import annotations

import csv
import io
import json
import re
import urllib.parse
from typing import Any, Dict, List, Optional, Sequence, Tuple

from .ai_investigation import (
    analyze_multi_traces,
    build_correlation_timeline,
    build_critical_path,
    build_investigation_replay,
    build_investigate_context,
    build_optimization_advice,
    check_task_budgets,
    compare_performance_metrics,
    compare_tasks_metrics,
    detect_anomalies,
    detect_priority_inversion,
    enrich_findings_with_ids,
    estimate_what_if,
    explain_regression,
    find_related_findings,
    conclusion_status_from_payload,
    generate_structured_report,
    max_tool_rounds_for_template,
    recommend_validation_experiments,
    resolve_finding,
    run_optimization_experiments,
    score_against_baseline,
    simulate_what_if,
    snapshot_from_summary,
)
from .html_report import (
    HTML_REPORT_TOC_CSS,
    HTML_REPORT_TOC_SCRIPT,
    btf_html_report_document,
    html_apply_collapsible_toc,
)
from .ai_planner import (
    assess_evidence_sufficiency,
    build_causal_chain,
    cluster_findings,
    detect_contradictions,
    find_similar_investigations,
    generate_experiment_plan,
    generate_fingerprint,
    plan_investigation,
    record_experiment_outcome,
    regression_localize,
    score_investigation_tool,
    suggest_scope,
)
from .ai_causal import (
    analyze_distribution,
    analyze_periodicity,
    analyze_temporal_causality,
    build_task_dependency_graph,
    challenge_conclusion,
    close_investigation,
    cluster_incidents,
    decompose_response_time,
    investigation_memory,
    rank_root_causes,
    summarize_investigation_context,
    verify_claim,
)

AI_TOOL_SET_CURSORS = "set_cursors"
AI_TOOL_ZOOM_TO_RANGE = "zoom_to_range"
AI_TOOL_HIGHLIGHT_TASK = "highlight_task"
AI_TOOL_SET_VIEW_MODE = "set_view_mode"
AI_TOOL_OPEN_CORRIDOR = "open_corridor_inspector"
AI_TOOL_ADD_ANNOTATION = "add_annotation"
AI_TOOL_QUERY_RAW_METRIC = "query_raw_metric"
AI_TOOL_EXPORT_REPORT = "export_report"
AI_TOOL_CLEAR_MARKS = "clear_marks"
AI_TOOL_RESET_VIEW = "reset_view"
AI_TOOL_SEARCH_TIMELINE = "search_timeline"
AI_TOOL_TRIGGER_COMPARE = "trigger_compare"
AI_TOOL_INVESTIGATE = "investigate"
AI_TOOL_DETECT_ANOMALIES = "detect_anomalies"
AI_TOOL_CORRELATE_EVENTS = "correlate_events"
AI_TOOL_FIND_CRITICAL_PATH = "find_critical_path"
AI_TOOL_COMPARE_PERFORMANCE = "compare_performance"
AI_TOOL_GENERATE_REPORT = "generate_report"
AI_TOOL_CHECK_BUDGET = "check_budget"
AI_TOOL_OPTIMIZE = "optimize"
AI_TOOL_REGRESSION_EXPLAIN = "regression_explain"
AI_TOOL_BOOKMARK_FINDING = "bookmark_finding"
AI_TOOL_INVESTIGATION_REPLAY = "investigation_replay"
AI_TOOL_WHAT_IF = "what_if"
AI_TOOL_OPTIMIZE_EXPERIMENT = "optimize_experiment"
AI_TOOL_ANALYZE_TRACES = "analyze_traces"
AI_TOOL_BASELINE_SCORE = "baseline_score"
AI_TOOL_RECOMMEND_EXPERIMENTS = "recommend_experiments"
AI_TOOL_EXPORT_INVESTIGATION = "export_investigation"
AI_TOOL_DETECT_PRIORITY_INVERSION = "detect_priority_inversion"
AI_TOOL_FIND_RELATED_FINDINGS = "find_related_findings"
AI_TOOL_COMPARE_TASKS = "compare_tasks"
AI_TOOL_EXPLAIN_FINDING = "explain_finding"
AI_TOOL_INTERPRET_QUERY = "interpret_query"
AI_TOOL_VALIDATE_EXPERIMENT = "validate_experiment"
AI_TOOL_MANAGE_HYPOTHESES = "manage_hypotheses"
AI_TOOL_PLAN_INVESTIGATION = "plan_investigation"
AI_TOOL_SUGGEST_SCOPE = "suggest_scope"
AI_TOOL_DETECT_CONTRADICTIONS = "detect_contradictions"
AI_TOOL_ASSESS_EVIDENCE_SUFFICIENCY = "assess_evidence_sufficiency"
AI_TOOL_CLUSTER_FINDINGS = "cluster_findings"
AI_TOOL_GENERATE_FINGERPRINT = "generate_fingerprint"
AI_TOOL_FIND_SIMILAR_INVESTIGATIONS = "find_similar_investigations"
AI_TOOL_REGRESSION_LOCALIZE = "regression_localize"
AI_TOOL_BUILD_CAUSAL_CHAIN = "build_causal_chain"
AI_TOOL_GENERATE_EXPERIMENT_PLAN = "generate_experiment_plan"
AI_TOOL_RECORD_EXPERIMENT_OUTCOME = "record_experiment_outcome"
AI_TOOL_SCORE_INVESTIGATION = "score_investigation"
AI_TOOL_ANALYZE_TEMPORAL_CAUSALITY = "analyze_temporal_causality"
AI_TOOL_BUILD_TASK_DEPENDENCY_GRAPH = "build_task_dependency_graph"
AI_TOOL_DECOMPOSE_RESPONSE_TIME = "decompose_response_time"
AI_TOOL_RANK_ROOT_CAUSES = "rank_root_causes"
AI_TOOL_VERIFY_CLAIM = "verify_claim"
AI_TOOL_CHALLENGE_CONCLUSION = "challenge_conclusion"
AI_TOOL_INVESTIGATION_MEMORY = "investigation_memory"
AI_TOOL_CLUSTER_INCIDENTS = "cluster_incidents"
AI_TOOL_CLOSE_INVESTIGATION = "close_investigation"
AI_TOOL_ANALYZE_DISTRIBUTION = "analyze_distribution"
AI_TOOL_ANALYZE_PERIODICITY = "analyze_periodicity"
AI_TOOL_SUMMARIZE_INVESTIGATION_CONTEXT = "summarize_investigation_context"

# Plan §8: capability class for each tool (description suffix; API-safe).
AI_TOOL_CAPABILITY_VIEWER_MUTATION = "viewer_mutation"
AI_TOOL_CAPABILITY_EXPORT = "export"
AI_TOOL_CAPABILITY_STORAGE = "storage"
AI_TOOL_CAPABILITY_HEURISTIC = "heuristic"
AI_TOOL_CAPABILITY_READ_ONLY = "read_only"

_AI_TOOL_CAPABILITY_BY_NAME: Dict[str, str] = {
    AI_TOOL_SET_CURSORS: AI_TOOL_CAPABILITY_VIEWER_MUTATION,
    AI_TOOL_ZOOM_TO_RANGE: AI_TOOL_CAPABILITY_VIEWER_MUTATION,
    AI_TOOL_HIGHLIGHT_TASK: AI_TOOL_CAPABILITY_VIEWER_MUTATION,
    AI_TOOL_SET_VIEW_MODE: AI_TOOL_CAPABILITY_VIEWER_MUTATION,
    AI_TOOL_OPEN_CORRIDOR: AI_TOOL_CAPABILITY_VIEWER_MUTATION,
    AI_TOOL_ADD_ANNOTATION: AI_TOOL_CAPABILITY_VIEWER_MUTATION,
    AI_TOOL_CLEAR_MARKS: AI_TOOL_CAPABILITY_VIEWER_MUTATION,
    AI_TOOL_RESET_VIEW: AI_TOOL_CAPABILITY_VIEWER_MUTATION,
    AI_TOOL_TRIGGER_COMPARE: AI_TOOL_CAPABILITY_VIEWER_MUTATION,
    AI_TOOL_BOOKMARK_FINDING: AI_TOOL_CAPABILITY_VIEWER_MUTATION,
    AI_TOOL_EXPORT_REPORT: AI_TOOL_CAPABILITY_EXPORT,
    AI_TOOL_EXPORT_INVESTIGATION: AI_TOOL_CAPABILITY_EXPORT,
    AI_TOOL_MANAGE_HYPOTHESES: AI_TOOL_CAPABILITY_STORAGE,
    AI_TOOL_INVESTIGATION_MEMORY: AI_TOOL_CAPABILITY_STORAGE,
    AI_TOOL_RECORD_EXPERIMENT_OUTCOME: AI_TOOL_CAPABILITY_STORAGE,
    AI_TOOL_CLOSE_INVESTIGATION: AI_TOOL_CAPABILITY_STORAGE,
    AI_TOOL_WHAT_IF: AI_TOOL_CAPABILITY_HEURISTIC,
    AI_TOOL_OPTIMIZE_EXPERIMENT: AI_TOOL_CAPABILITY_HEURISTIC,
    AI_TOOL_OPTIMIZE: AI_TOOL_CAPABILITY_HEURISTIC,
    AI_TOOL_RECOMMEND_EXPERIMENTS: AI_TOOL_CAPABILITY_HEURISTIC,
    AI_TOOL_GENERATE_EXPERIMENT_PLAN: AI_TOOL_CAPABILITY_HEURISTIC,
    AI_TOOL_BASELINE_SCORE: AI_TOOL_CAPABILITY_HEURISTIC,
}


def ai_tool_capability(name: Any) -> str:
    """Capability class for a viewer tool name."""
    key = str(name or "").strip()
    return _AI_TOOL_CAPABILITY_BY_NAME.get(key, AI_TOOL_CAPABILITY_READ_ONLY)


def annotate_tool_capabilities(
    tools: Optional[Sequence[Dict[str, Any]]] = None,
) -> List[Dict[str, Any]]:
    """Append ``[capability: …]`` to each tool description (Desktop/Web parity)."""
    out: List[Dict[str, Any]] = []
    for tool in tools or []:
        if not isinstance(tool, dict):
            continue
        copied = dict(tool)
        fn = copied.get("function")
        if not isinstance(fn, dict):
            out.append(copied)
            continue
        fn = dict(fn)
        name = str(fn.get("name") or "").strip()
        cap = ai_tool_capability(name)
        desc = str(fn.get("description") or "").rstrip()
        tag = f"[capability: {cap}]"
        if tag not in desc:
            fn["description"] = f"{desc} {tag}".strip() if desc else tag
        copied["function"] = fn
        out.append(copied)
    return out


AI_VIEWER_TOOL_NAMES: Tuple[str, ...] = (
    AI_TOOL_SET_CURSORS,
    AI_TOOL_ZOOM_TO_RANGE,
    AI_TOOL_HIGHLIGHT_TASK,
    AI_TOOL_SET_VIEW_MODE,
    AI_TOOL_OPEN_CORRIDOR,
    AI_TOOL_ADD_ANNOTATION,
    AI_TOOL_QUERY_RAW_METRIC,
    AI_TOOL_EXPORT_REPORT,
    AI_TOOL_CLEAR_MARKS,
    AI_TOOL_RESET_VIEW,
    AI_TOOL_SEARCH_TIMELINE,
    AI_TOOL_TRIGGER_COMPARE,
    AI_TOOL_INVESTIGATE,
    AI_TOOL_DETECT_ANOMALIES,
    AI_TOOL_CORRELATE_EVENTS,
    AI_TOOL_FIND_CRITICAL_PATH,
    AI_TOOL_COMPARE_PERFORMANCE,
    AI_TOOL_GENERATE_REPORT,
    AI_TOOL_CHECK_BUDGET,
    AI_TOOL_OPTIMIZE,
    AI_TOOL_REGRESSION_EXPLAIN,
    AI_TOOL_BOOKMARK_FINDING,
    AI_TOOL_INVESTIGATION_REPLAY,
    AI_TOOL_WHAT_IF,
    AI_TOOL_OPTIMIZE_EXPERIMENT,
    AI_TOOL_ANALYZE_TRACES,
    AI_TOOL_BASELINE_SCORE,
    AI_TOOL_RECOMMEND_EXPERIMENTS,
    AI_TOOL_EXPORT_INVESTIGATION,
    AI_TOOL_DETECT_PRIORITY_INVERSION,
    AI_TOOL_FIND_RELATED_FINDINGS,
    AI_TOOL_COMPARE_TASKS,
    AI_TOOL_EXPLAIN_FINDING,
    AI_TOOL_INTERPRET_QUERY,
    AI_TOOL_VALIDATE_EXPERIMENT,
    AI_TOOL_MANAGE_HYPOTHESES,
    AI_TOOL_PLAN_INVESTIGATION,
    AI_TOOL_SUGGEST_SCOPE,
    AI_TOOL_DETECT_CONTRADICTIONS,
    AI_TOOL_ASSESS_EVIDENCE_SUFFICIENCY,
    AI_TOOL_CLUSTER_FINDINGS,
    AI_TOOL_GENERATE_FINGERPRINT,
    AI_TOOL_FIND_SIMILAR_INVESTIGATIONS,
    AI_TOOL_REGRESSION_LOCALIZE,
    AI_TOOL_BUILD_CAUSAL_CHAIN,
    AI_TOOL_GENERATE_EXPERIMENT_PLAN,
    AI_TOOL_RECORD_EXPERIMENT_OUTCOME,
    AI_TOOL_SCORE_INVESTIGATION,
    AI_TOOL_ANALYZE_TEMPORAL_CAUSALITY,
    AI_TOOL_BUILD_TASK_DEPENDENCY_GRAPH,
    AI_TOOL_DECOMPOSE_RESPONSE_TIME,
    AI_TOOL_RANK_ROOT_CAUSES,
    AI_TOOL_VERIFY_CLAIM,
    AI_TOOL_CHALLENGE_CONCLUSION,
    AI_TOOL_INVESTIGATION_MEMORY,
    AI_TOOL_CLUSTER_INCIDENTS,
    AI_TOOL_CLOSE_INVESTIGATION,
    AI_TOOL_ANALYZE_DISTRIBUTION,
    AI_TOOL_ANALYZE_PERIODICITY,
    AI_TOOL_SUMMARIZE_INVESTIGATION_CONTEXT,
)

AI_BOOKMARK_KINDS: Tuple[str, ...] = (
    "root_cause", "evidence", "correlated", "reference",
)

AI_FIND_MODES: Tuple[str, ...] = (
    "contains", "exact", "regex", "sti", "tags", "intervals",
    "lifecycle", "pointers", "migrations",
)
AI_CLEAR_MARKS_TARGETS: Tuple[str, ...] = (
    "annotations", "cursors", "bookmarks", "all", "everything",
)

AI_RAW_METRIC_PRIORITY = "priority_inheritance"
AI_RAW_METRIC_EXECUTION = "execution"
AI_RAW_METRIC_MIGRATIONS = "migrations"
AI_RAW_METRIC_BLOCKING = "blocking"
AI_RAW_METRIC_SYNC = "sync"
AI_RAW_METRIC_FINDINGS = "findings"
AI_RAW_METRIC_NAMES: Tuple[str, ...] = (
    AI_RAW_METRIC_PRIORITY,
    AI_RAW_METRIC_EXECUTION,
    AI_RAW_METRIC_MIGRATIONS,
    AI_RAW_METRIC_BLOCKING,
    AI_RAW_METRIC_SYNC,
    AI_RAW_METRIC_FINDINGS,
)
_RAW_METRIC_ALIASES = {
    "priority_inheritance": AI_RAW_METRIC_PRIORITY,
    "priority": AI_RAW_METRIC_PRIORITY,
    "pi": AI_RAW_METRIC_PRIORITY,
    "inversion": AI_RAW_METRIC_PRIORITY,
    "inherit": AI_RAW_METRIC_PRIORITY,
    "execution": AI_RAW_METRIC_EXECUTION,
    "wcet": AI_RAW_METRIC_EXECUTION,
    "cpu": AI_RAW_METRIC_EXECUTION,
    "slices": AI_RAW_METRIC_EXECUTION,
    "run": AI_RAW_METRIC_EXECUTION,
    "migrations": AI_RAW_METRIC_MIGRATIONS,
    "migration": AI_RAW_METRIC_MIGRATIONS,
    "migr": AI_RAW_METRIC_MIGRATIONS,
    "thrash": AI_RAW_METRIC_MIGRATIONS,
    "blocking": AI_RAW_METRIC_BLOCKING,
    "block": AI_RAW_METRIC_BLOCKING,
    "wait": AI_RAW_METRIC_BLOCKING,
    "latency": AI_RAW_METRIC_BLOCKING,
    "sync": AI_RAW_METRIC_SYNC,
    "mutex": AI_RAW_METRIC_SYNC,
    "semaphore": AI_RAW_METRIC_SYNC,
    "lock": AI_RAW_METRIC_SYNC,
    "findings": AI_RAW_METRIC_FINDINGS,
    "finding": AI_RAW_METRIC_FINDINGS,
    "analysis": AI_RAW_METRIC_FINDINGS,
}
_MAX_RAW_METRIC_ROWS = 40
_MAX_SEARCH_HITS = 40
_MAX_ANNOTATION_NOTE = 240

# QTextBrowser truncates ``scheme:digits`` (treats it as host:port). Use a path.
_BTF_JUMP_HREF_RE = re.compile(
    r"btfjump:(?://)?(?:time/)?([0-9]+(?:\.[0-9]+)?)",
    re.IGNORECASE,
)
_BTF_RANGE_HREF_RE = re.compile(
    r"btfrange:(?://)?(?:lo/)?([0-9]+(?:\.[0-9]+)?)/([0-9]+(?:\.[0-9]+)?)",
    re.IGNORECASE,
)
_BTF_HIGHLIGHT_HREF_RE = re.compile(
    r"btfhighlight:(?://)?(?:task/)?(.+)$",
    re.IGNORECASE,
)


def btf_jump_href(value: Any) -> str:
    """Chat href for ``jump:TIME`` that survives QTextBrowser ``setHtml``."""
    try:
        n = float(value)
    except (TypeError, ValueError):
        return "btfjump:time/0"
    token = str(int(n)) if n.is_integer() else str(n)
    return f"btfjump:time/{token}"


def parse_btf_jump_href(href: Any) -> Optional[float]:
    """Parse ``btfjump:time/N`` or legacy ``btfjump:N``."""
    m = _BTF_JUMP_HREF_RE.search(str(href or ""))
    if not m:
        return None
    try:
        return float(m.group(1))
    except (TypeError, ValueError):
        return None


def btf_range_href(lo: Any, hi: Any) -> str:
    """Chat href for ``range:LO/HI`` that survives QTextBrowser ``setHtml``."""
    def _tok(value: Any) -> str:
        try:
            n = float(value)
        except (TypeError, ValueError):
            return "0"
        return str(int(n)) if n.is_integer() else str(n)
    return f"btfrange:{_tok(lo)}/{_tok(hi)}"


def parse_btf_range_href(href: Any) -> Optional[Tuple[float, float]]:
    """Parse ``btfrange:LO/HI``."""
    m = _BTF_RANGE_HREF_RE.search(str(href or ""))
    if not m:
        return None
    try:
        return float(m.group(1)), float(m.group(2))
    except (TypeError, ValueError):
        return None


def btf_highlight_href(name: str) -> str:
    """Chat href for a highlight target (slash form + percent-encoding)."""
    token = urllib.parse.quote(str(name or "").strip(), safe="")
    return f"btfhighlight:task/{token}"


def parse_btf_highlight_href(href: Any) -> str:
    """Parse ``btfhighlight:task/…`` or legacy ``btfhighlight:Name``."""
    m = _BTF_HIGHLIGHT_HREF_RE.search(str(href or "").strip())
    if not m:
        return ""
    return urllib.parse.unquote(m.group(1).strip().lstrip("/"))


_BTF_STATS_HREF_RE = re.compile(
    r"^btfstats:(?:section/)?([A-Za-z0-9_\-]+)$", re.IGNORECASE)


def btf_stats_href(section_id: str) -> str:
    """Chat href that opens a Statistics section (Evidence Navigation)."""
    sid = str(section_id or "").strip()
    return f"btfstats:section/{sid}" if sid else "btfstats:section/"


def parse_btf_stats_href(href: Any) -> str:
    """Parse ``btfstats:section/SID`` or ``btfstats:SID``."""
    raw = str(href or "").strip()
    m = _BTF_STATS_HREF_RE.match(raw)
    if m:
        return str(m.group(1) or "").strip()
    low = raw.lower()
    if low.startswith("btfstats:"):
        return raw.split(":", 1)[1].strip().lstrip("/").removeprefix("section/").strip()
    return ""

# Tool-use policy (also AI_TOOL_PROMPT). Keep in sync with web aiTools.js.
AI_TOOL_PROMPT = ("Use native tools only when evidence or an explicit viewer action requires them.\n\n1. Establish scope, subject, and comparison direction.\n2. Use the minimum sufficient evidence tool.\n3. Check missing links, contradictions, and credible alternatives.\n4. Continue only if another result could change the verdict.\n5. Verify before asserting a high-confidence root cause.\n\n- Use planning tools only for broad or ambiguous investigations.\n- Use exact metric or timeline tools when summaries lack required evidence.\n- For comparisons, A is candidate, B is baseline, and delta = A - B.\n- Use simulation or optimization only when requested.\n- Generate a report when requested. For Report mode or an explicit save/download,\n  call export_report after generate_report; otherwise export only when asked.\n- Analysis alone does not authorize viewer changes. Apply viewer changes only\n  when explicitly requested or promised by the selected workflow.\n- Stop when evidence is sufficient or tools cannot resolve the uncertainty.\n- Empty tool results mean no matching data in scope; say so and do not invent\n  values. Failed tools are failures \u2014 never claim the action or export succeeded.\n- Never claim an unconfirmed result, viewer change, or export.\n- After tools, separate retrieved evidence from applied viewer changes.\n- Use Mermaid only when it clarifies a supported relationship and the mode\n  permits it.").rstrip("\n")
AI_TOOL_SYSTEM_ADDENDUM = AI_TOOL_PROMPT

AI_MERMAID_SEQUENCE_EXAMPLE = """```mermaid
sequenceDiagram
  autonumber
  participant L as Low[266] (Core 0)
  participant M as Med[267] (Core 0)
  participant H as High[268] (Core 0)
  L->>Mutex(0x80018700): take
  M->>Core 0: runs work
  H->>Mutex(0x80018700): take (Blocked)
  Note over L: Kernel boosts Low -> Pri 4
  L->>Mutex(0x80018700): give
  H->>Mutex(0x80018700): acquires lock
```"""

AI_MERMAID_MIGRATION_EXAMPLE = """```mermaid
graph LR
  C0[Core_0] -->|12| C1[Core_1]
  C1 -->|3| C0
```"""

_MAX_CURSORS_TOOL = 8
_MAX_TOOL_ROUNDS = 4


def ai_viewer_tools_for_mode(mode: Any = None, stage: Any = "") -> List[Dict[str, Any]]:
    """Tool schemas for Settings → AI context mode (Full = complete catalog)."""
    from .ai_case import filter_tools_for_context_mode
    return filter_tools_for_context_mode(ai_viewer_tools(), mode, stage)


def ai_viewer_tools() -> List[Dict[str, Any]]:
    """OpenAI-compatible ``tools`` array."""
    return annotate_tool_capabilities([
        {
            "type": "function",
            "function": {
                "name": AI_TOOL_SET_CURSORS,
                "description": (
                    "Clear existing cursors and place new ones at the given "
                    "trace timestamps. Enables Limit to C1–Cn statistics when "
                    "two or more cursors are placed."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "timestamps": {
                            "type": "array",
                            "items": {"type": "number"},
                            "description": (
                                "trace_time_unit timestamps (same unit as jump:TIME), "
                                "earliest to latest. 1–8 values."
                            ),
                        },
                    },
                    "required": ["timestamps"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": AI_TOOL_ZOOM_TO_RANGE,
                "description": "Zoom and pan the timeline so start_time..end_time fills the view.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "start_time": {
                            "type": "number",
                            "description": "Range start in trace_time_unit (same as jump:TIME).",
                        },
                        "end_time": {
                            "type": "number",
                            "description": "Range end in trace_time_unit (same as jump:TIME).",
                        },
                    },
                    "required": ["start_time", "end_time"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": AI_TOOL_HIGHLIGHT_TASK,
                "description": (
                    "Lock-highlight a task on the timeline (Task View). "
                    "Pass empty string to clear the highlight."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "task_name_or_id": {
                            "type": "string",
                            "description": (
                                "Task display name (e.g. Low[266]), merge key, "
                                "or numeric task id."
                            ),
                        },
                    },
                    "required": ["task_name_or_id"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": AI_TOOL_SET_VIEW_MODE,
                "description": "Switch Task View vs Core View and optional timeline orientation.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "mode": {
                            "type": "string",
                            "enum": ["task", "core"],
                            "description": "task = one row per task; core = one row per core.",
                        },
                        "orientation": {
                            "type": "string",
                            "enum": ["horizontal", "vertical"],
                            "description": "Optional layout orientation.",
                        },
                    },
                    "required": ["mode"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": AI_TOOL_OPEN_CORRIDOR,
                "description": (
                    "Open the Migration & Corridor Inspector. Optionally focus a "
                    "directed core pair (e.g. Core_0 → Core_1)."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "core_from": {
                            "type": "string",
                            "description": "Source core name (e.g. Core_0).",
                        },
                        "core_to": {
                            "type": "string",
                            "description": "Destination core name (e.g. Core_1).",
                        },
                    },
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": AI_TOOL_ADD_ANNOTATION,
                "description": (
                    "Place an orange timeline annotation at a timestamp "
                    "(same unit as jump:TIME) and jump there. Use this to mark "
                    "anomalous spikes, inversion windows, or other points of interest."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "time": {
                            "type": "number",
                            "description": "Trace time-unit timestamp.",
                        },
                        "note": {
                            "type": "string",
                            "description": "Short annotation label shown on the Marks panel.",
                        },
                    },
                    "required": ["time", "note"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": AI_TOOL_QUERY_RAW_METRIC,
                "description": (
                    "Read the underlying per-task metric series for the current "
                    "Statistics scope (cursor range when Limit to C1–Cn is on). "
                    "Returns JSON samples — not a GUI change. Metrics: "
                    "priority_inheritance, execution, migrations, blocking, "
                    "sync, findings."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "task": {
                            "type": "string",
                            "description": (
                                "Task display name (e.g. Low[266]), merge key, "
                                "or numeric task id."
                            ),
                        },
                        "metric": {
                            "type": "string",
                            "enum": list(AI_RAW_METRIC_NAMES),
                            "description": "Which series to return.",
                        },
                    },
                    "required": ["task", "metric"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": AI_TOOL_EXPORT_REPORT,
                "description": (
                    "Download a report bundling Analysis Findings, the AI "
                    "conversation (including mermaid diagrams), annotations, "
                    "and the current GUI state (cursors, highlight, view)."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "format": {
                            "type": "string",
                            "enum": ["html", "csv", "json"],
                            "description": (
                                "html (default), csv, or json (full "
                                "investigation package — see export_investigation)."
                            ),
                        },
                    },
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": AI_TOOL_CLEAR_MARKS,
                "description": (
                    "Clear timeline clutter before focusing a new issue. "
                    "all = annotations + cursors (default). everything also "
                    "clears bookmarks."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "what": {
                            "type": "string",
                            "enum": list(AI_CLEAR_MARKS_TARGETS),
                            "description": (
                                "annotations, cursors, bookmarks, all "
                                "(annotations+cursors), or everything."
                            ),
                        },
                    },
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": AI_TOOL_RESET_VIEW,
                "description": (
                    "Fit the timeline to the full trace span and clear the "
                    "task highlight. Does not remove cursors or annotations."
                ),
                "parameters": {"type": "object", "properties": {}},
            },
        },
        {
            "type": "function",
            "function": {
                "name": AI_TOOL_SEARCH_TIMELINE,
                "description": (
                    "Search the trace like Find (Ctrl+F). Returns matching "
                    "timestamps for task names, STI/tag notes, intervals, "
                    "lifecycle events, sync pointers, or migrations."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "Text, tag value, pointer, or task name.",
                        },
                        "mode": {
                            "type": "string",
                            "enum": list(AI_FIND_MODES),
                            "description": (
                                "contains (default), exact, regex, sti, tags, "
                                "intervals, lifecycle, pointers, migrations."
                            ),
                        },
                    },
                    "required": ["query"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": AI_TOOL_TRIGGER_COMPARE,
                "description": (
                    "Compare two loaded trace tabs (Trace Compare). Returns "
                    "diff tables as CSV. Optional tab names or 0-based indices."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "tab_a": {
                            "type": "string",
                            "description": "First tab name or 0-based tab index (default 0).",
                        },
                        "tab_b": {
                            "type": "string",
                            "description": "Second tab name or 0-based tab index (default 1).",
                        },
                    },
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": AI_TOOL_INVESTIGATE,
                "description": (
                    "Build a structured investigation context for one Analysis "
                    "Finding (hypotheses, evidence chain, suggested next tools). "
                    "Call this first during Investigate / Root cause workflows. "
                    "finding_id may be the finding id, 1-based index, or title "
                    "substring; omit to focus the top warning/error."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "finding_id": {
                            "type": "string",
                            "description": (
                                "Finding id (e.g. thrashing), 1-based index, "
                                "or title substring. Empty = top actionable finding."
                            ),
                        },
                        "depth": {
                            "type": "integer",
                            "description": "Investigation depth 1–5 (default 2).",
                        },
                    },
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": AI_TOOL_DETECT_ANOMALIES,
                "description": (
                    "Rank Analysis Findings as Critical / Warning / Info anomalies "
                    "(WCET spikes, thrashing, blocking, inversion, deadlines, …)."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "limit": {
                            "type": "integer",
                            "description": "Max anomalies to return (1–40, default 10).",
                        },
                    },
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": AI_TOOL_CORRELATE_EVENTS,
                "description": (
                    "Cross-task/cross-metric timeline correlation for a task: "
                    "merge blocking, execution, migrations, sync, priority "
                    "inheritance, and Find hits into one ordered event list."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "task": {
                            "type": "string",
                            "description": "Task display name, id, or merge key.",
                        },
                        "around_time": {
                            "type": "number",
                            "description": "Optional center time (trace units).",
                        },
                        "window": {
                            "type": "number",
                            "description": "Half-width around around_time (trace units).",
                        },
                    },
                    "required": ["task"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": AI_TOOL_FIND_CRITICAL_PATH,
                "description": (
                    "Build a preempt/block/mutex critical path for a task around "
                    "a timestamp by correlating blocking, sync, priority, execution, "
                    "and migration events."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "task": {
                            "type": "string",
                            "description": "Task display name, id, or merge key.",
                        },
                        "timestamp": {
                            "type": "number",
                            "description": "Optional center time (trace units).",
                        },
                        "window": {
                            "type": "number",
                            "description": "Half-width around timestamp (default 2000).",
                        },
                    },
                    "required": ["task"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": AI_TOOL_COMPARE_PERFORMANCE,
                "description": (
                    "Structured performance deltas between two open tabs "
                    "(regression rules + confidence). Prefer this over raw CSV "
                    "when explaining A vs B; trigger_compare still opens the dialog."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "tab_a": {
                            "type": "string",
                            "description": "Candidate tab (index or name).",
                        },
                        "tab_b": {
                            "type": "string",
                            "description": "Baseline tab (index or name).",
                        },
                    },
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": AI_TOOL_GENERATE_REPORT,
                "description": (
                    "Build a typed engineering markdown report from Analysis "
                    "Findings (executive / performance / root_cause / regression / "
                    "optimization / bug / ci). Does not save a file — call "
                    "export_report afterward to download HTML/CSV."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "report_type": {
                            "type": "string",
                            "description": (
                                "executive|performance|root_cause|regression|"
                                "optimization|bug|ci"
                            ),
                        },
                        "finding_id": {
                            "type": "string",
                            "description": "Optional focus finding id / index / title.",
                        },
                    },
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": AI_TOOL_CHECK_BUDGET,
                "description": (
                    "Compare per-task WCET / response / deadline metrics against "
                    "optional budgets. Omit tasks to let the host build rows from "
                    "Analysis Findings task names."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "budgets": {
                            "type": "object",
                            "description": (
                                "Map of task → {wcet_us, response_us, deadline_us} "
                                "(values in microseconds)."
                            ),
                        },
                        "tasks": {
                            "type": "array",
                            "description": (
                                "Optional metric rows: {task, wcet_us?, response_us?, "
                                "deadline_us?, exec_max_us?, blocking_max_us?} "
                                "(*_us fields in microseconds)."
                            ),
                        },
                    },
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": AI_TOOL_OPTIMIZE,
                "description": (
                    "Evidence-backed optimization / mitigation ideas from Analysis "
                    "Findings (labelled as estimates, not measured behavior)."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "limit": {
                            "type": "integer",
                            "description": "Max recommendations (1–20, default 5).",
                        },
                    },
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": AI_TOOL_REGRESSION_EXPLAIN,
                "description": (
                    "Explain the primary A vs B regression after comparing two "
                    "open tabs (runs compare_performance then narrates)."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "tab_a": {
                            "type": "string",
                            "description": "Candidate tab (index or name).",
                        },
                        "tab_b": {
                            "type": "string",
                            "description": "Baseline tab (index or name).",
                        },
                    },
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": AI_TOOL_BOOKMARK_FINDING,
                "description": (
                    "Pin a semantic investigation annotation at a timestamp "
                    "(root_cause / evidence / correlated / reference). GUI mutate."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "time": {
                            "type": "number",
                            "description": "Trace time-unit timestamp.",
                        },
                        "kind": {
                            "type": "string",
                            "enum": list(AI_BOOKMARK_KINDS),
                            "description": (
                                "root_cause | evidence | correlated | reference"
                            ),
                        },
                        "note": {
                            "type": "string",
                            "description": "Optional short note appended to the label.",
                        },
                    },
                    "required": ["time", "kind"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": AI_TOOL_INVESTIGATION_REPLAY,
                "description": (
                    "Build a structured investigation-replay card (steps, tools "
                    "run, conclusion, evidence times) for UI / export."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "finding_id": {
                            "type": "string",
                            "description": "Finding id / index / title substring.",
                        },
                        "conclusion": {
                            "type": "string",
                            "description": "Short investigation conclusion text.",
                        },
                        "tools_run": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "Tool names already executed.",
                        },
                        "evidence_times": {
                            "type": "array",
                            "items": {"type": "number"},
                            "description": "Evidence timestamps for cursor replay.",
                        },
                    },
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": AI_TOOL_WHAT_IF,
                "description": (
                    "Heuristic what-if simulation from measured execution slices, "
                    "migrations, blocking gaps, and core util (not an RTOS kernel)."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "change": {
                            "type": "string",
                            "description": (
                                "Proposed change, e.g. pin CS[28] to Core_0, "
                                "raise priority, reduce mutex contention 50%."
                            ),
                        },
                        "task": {
                            "type": "string",
                            "description": "Optional focus task (inferred from change when omitted).",
                        },
                    },
                    "required": ["change"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": AI_TOOL_OPTIMIZE_EXPERIMENT,
                "description": (
                    "Run a small set of automatic optimization experiments "
                    "(pin/priority/contention/migration) via the heuristic "
                    "simulator and rank by estimated cost improvement."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "task": {
                            "type": "string",
                            "description": "Focus task (defaults from top finding).",
                        },
                        "limit": {
                            "type": "integer",
                            "description": "Max experiments (1–12, default 5).",
                        },
                    },
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": AI_TOOL_ANALYZE_TRACES,
                "description": (
                    "Rank all loaded trace tabs by scheduling behavior "
                    "(load balance, migrations, missed ticks)."
                ),
                "parameters": {"type": "object", "properties": {}},
            },
        },
        {
            "type": "function",
            "function": {
                "name": AI_TOOL_BASELINE_SCORE,
                "description": (
                    "Score current per-task metrics (WCET, blocking, "
                    "migrations, response) against a stored historical "
                    "baseline; flags entries where |z| > 2."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "task": {
                            "type": "string",
                            "description": "Optional focus task filter.",
                        },
                        "baseline": {
                            "type": "object",
                            "description": (
                                "Optional baseline profile object (defaults "
                                "to the host's stored profile)."
                            ),
                        },
                        "snapshot": {
                            "type": "object",
                            "description": (
                                "Optional {tasks: {task: {wcet_us, "
                                "blocking_us, migrations, response_us}}} "
                                "snapshot (*_us in microseconds; defaults to "
                                "the host's current trace metrics)."
                            ),
                        },
                    },
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": AI_TOOL_RECOMMEND_EXPERIMENTS,
                "description": (
                    "Suggest validation experiments (simulation / firmware / "
                    "measurement) for a finding or task, using heuristics "
                    "(thrash→pin, mutex→shorten critical section, etc.)."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "finding_id": {
                            "type": "string",
                            "description": "Finding id / index / title substring.",
                        },
                        "task": {
                            "type": "string",
                            "description": "Optional focus task.",
                        },
                        "limit": {
                            "type": "integer",
                            "description": "Max experiments (1–20, default 5).",
                        },
                    },
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": AI_TOOL_EXPORT_INVESTIGATION,
                "description": (
                    "Download the completed investigation (finding, tools "
                    "run, queries, evidence, conclusion, confidence, "
                    "alternatives) as a JSON package."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "finding_id": {
                            "type": "string",
                            "description": "Finding id / index / title substring.",
                        },
                        "conclusion": {
                            "type": "string",
                            "description": "Short investigation conclusion text.",
                        },
                        "tools_run": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "Tool names already executed.",
                        },
                        "evidence_times": {
                            "type": "array",
                            "items": {"type": "number"},
                            "description": "Evidence timestamps for cursor replay.",
                        },
                    },
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": AI_TOOL_DETECT_PRIORITY_INVERSION,
                "description": (
                    "Scan priority-inheritance boost episodes flagged as "
                    "inversion suspects (L/M/H pattern) and return "
                    "high/medium/low task, mutex, time, and duration for each."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "task": {
                            "type": "string",
                            "description": (
                                "Optional focus task (low or medium task name); "
                                "omit to scan all tasks."
                            ),
                        },
                        "window": {
                            "type": "number",
                            "description": (
                                "Optional minimum episode duration (ns) to "
                                "ignore trivial boosts."
                            ),
                        },
                    },
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": AI_TOOL_FIND_RELATED_FINDINGS,
                "description": (
                    "Relate Analysis Findings by shared task, metric keyword, "
                    "evidence-time proximity, or severity adjacency."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "finding_id": {
                            "type": "string",
                            "description": "Focus finding id / index / title substring.",
                        },
                        "task": {
                            "type": "string",
                            "description": "Optional task filter.",
                        },
                        "metric": {
                            "type": "string",
                            "description": (
                                "Optional metric filter: priority_inheritance|"
                                "execution|migrations|blocking|sync|findings."
                            ),
                        },
                        "window": {
                            "type": "number",
                            "description": (
                                "Optional evidence-time proximity window (ns) "
                                "relative to the focus finding."
                            ),
                        },
                        "limit": {
                            "type": "integer",
                            "description": "Max related findings (1–40, default 10).",
                        },
                    },
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": AI_TOOL_COMPARE_TASKS,
                "description": (
                    "Compare two tasks' execution / blocking / migrations / "
                    "priority-inheritance metrics side by side with deltas."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "task_a": {
                            "type": "string",
                            "description": "First task display name, id, or merge key.",
                        },
                        "task_b": {
                            "type": "string",
                            "description": "Second task display name, id, or merge key.",
                        },
                        "metrics": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": (
                                "Optional subset of execution|blocking|"
                                "migrations|priority_inheritance (default all)."
                            ),
                        },
                    },
                    "required": ["task_a", "task_b"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": AI_TOOL_EXPLAIN_FINDING,
                "description": (
                    "Explain one Analysis Finding at quick, technical, or deep "
                    "level. Host-side: uses the finding text plus hypotheses."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "finding_id": {
                            "type": "string",
                            "description": "Finding id, 1-based index, or title substring.",
                        },
                        "level": {
                            "type": "string",
                            "enum": ["quick", "technical", "deep"],
                            "description": "Explanation depth (default technical).",
                        },
                    },
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": AI_TOOL_INTERPRET_QUERY,
                "description": (
                    "Turn a free-form question into an explicit investigation "
                    "scope (mode, areas, finding_id) before running tools."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "question": {
                            "type": "string",
                            "description": "The user's natural-language question.",
                        },
                    },
                    "required": ["question"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": AI_TOOL_VALIDATE_EXPERIMENT,
                "description": (
                    "Compare expected experiment deltas (percent) with actual "
                    "A vs B / what-if results. Returns VALIDATED / PARTIALLY "
                    "VALIDATED / DISPROVED."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "expected": {
                            "type": "object",
                            "description": "Metric → expected signed percent change.",
                        },
                        "actual": {
                            "type": "object",
                            "description": "Metric → measured signed percent change.",
                        },
                    },
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": AI_TOOL_MANAGE_HYPOTHESES,
                "description": (
                    "Mark one investigation hypothesis as supported, possible, "
                    "rejected, or need_evidence."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "hypothesis_id": {
                            "type": "string",
                            "description": "Hypothesis id (h1), 1-based index, or name.",
                        },
                        "status": {
                            "type": "string",
                            "enum": ["supported", "possible", "rejected", "need_evidence"],
                            "description": (
                                "supported | possible | rejected | need_evidence."
                            ),
                        },
                        "reason": {
                            "type": "string",
                            "description": "Optional why this status was chosen.",
                        },
                        "finding_id": {
                            "type": "string",
                            "description": "Finding to load hypotheses from if omitted.",
                        },
                    },
                    "required": ["hypothesis_id", "status"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": AI_TOOL_PLAN_INVESTIGATION,
                "description": (
                    "Plan the cheapest tool sequence and rank hypotheses before "
                    "running the rest of an investigation."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "question": {"type": "string"},
                        "finding_id": {"type": "string"},
                    },
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": AI_TOOL_SUGGEST_SCOPE,
                "description": (
                    "Recommend task / related tasks / time window before "
                    "Limit to C1–Cn."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "question": {"type": "string"},
                    },
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": AI_TOOL_DETECT_CONTRADICTIONS,
                "description": (
                    "Test whether current metrics/findings contradict the "
                    "leading hypothesis."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "hypothesis": {"type": "string"},
                        "metrics": {"type": "object"},
                    },
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": AI_TOOL_ASSESS_EVIDENCE_SUFFICIENCY,
                "description": (
                    "Decide whether to STOP INVESTIGATION, continue, or revise "
                    "the hypothesis."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "tools_run": {
                            "type": "array",
                            "items": {"type": "string"},
                        },
                    },
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": AI_TOOL_CLUSTER_FINDINGS,
                "description": "Group related Analysis Findings into one incident.",
                "parameters": {"type": "object", "properties": {}},
            },
        },
        {
            "type": "function",
            "function": {
                "name": AI_TOOL_GENERATE_FINGERPRINT,
                "description": "Compact scheduling/sync/timing signature of this trace.",
                "parameters": {"type": "object", "properties": {}},
            },
        },
        {
            "type": "function",
            "function": {
                "name": AI_TOOL_FIND_SIMILAR_INVESTIGATIONS,
                "description": "Match this trace fingerprint against recorded outcomes.",
                "parameters": {
                    "type": "object",
                    "properties": {"limit": {"type": "integer"}},
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": AI_TOOL_REGRESSION_LOCALIZE,
                "description": (
                    "Localize A vs B execution inflation to a task and time region."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "label_a": {"type": "string"},
                        "label_b": {"type": "string"},
                    },
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": AI_TOOL_BUILD_CAUSAL_CHAIN,
                "description": (
                    "Build a causal/correlated/temporal chain. Correlation is "
                    "never silently treated as causation."
                ),
                "parameters": {"type": "object", "properties": {}},
            },
        },
        {
            "type": "function",
            "function": {
                "name": AI_TOOL_GENERATE_EXPERIMENT_PLAN,
                "description": "Propose ranked firmware / what-if experiments.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "task": {"type": "string"},
                        "limit": {"type": "integer"},
                    },
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": AI_TOOL_RECORD_EXPERIMENT_OUTCOME,
                "description": (
                    "Store predicted vs actual experiment results to improve "
                    "future recommendations."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "change": {"type": "string"},
                        "predicted": {"type": "string"},
                        "actual": {"type": "string"},
                        "quality": {"type": "string"},
                    },
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": AI_TOOL_SCORE_INVESTIGATION,
                "description": (
                    "Score evidence efficiency, cost, false-confidence, "
                    "falsification, scope accuracy, and stop efficiency."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "tools_run": {
                            "type": "array",
                            "items": {"type": "string"},
                        },
                        "conclusion": {"type": "string"},
                        "confidence": {
                            "type": "string",
                            "enum": ["high", "medium", "low"],
                            "description": "Confidence band: high | medium | low.",
                        },
                        "elapsed_s": {"type": "number"},
                    },
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": AI_TOOL_ANALYZE_TEMPORAL_CAUSALITY,
                "description": (
                    "Order Analysis Findings in time into a happens-before chain "
                    "(heuristic; not a kernel replay)."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {"task": {"type": "string"}},
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": AI_TOOL_BUILD_TASK_DEPENDENCY_GRAPH,
                "description": (
                    "Build a task/resource dependency graph from BTF sync holds, "
                    "preemption chains, migrations, and priority inheritance "
                    "(falls back to finding wording). Optional task keeps a "
                    "2-hop neighborhood and lists upstream tasks."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {"task": {"type": "string"}},
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": AI_TOOL_DECOMPOSE_RESPONSE_TIME,
                "description": (
                    "Split delay into mutex, preemption, migration, execution, "
                    "and scheduler shares (relative magnitudes)."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {"task": {"type": "string"}},
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": AI_TOOL_RANK_ROOT_CAUSES,
                "description": "Rank likely root causes from findings or hypotheses.",
                "parameters": {"type": "object", "properties": {}},
            },
        },
        {
            "type": "function",
            "function": {
                "name": AI_TOOL_VERIFY_CLAIM,
                "description": (
                    "Check a causal claim against findings and optional cursor "
                    "scope. Always pass claim as a non-empty string stating the "
                    "hypothesis to verify. Verdict: confirmed | rejected | "
                    "inconclusive."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "claim": {
                            "type": "string",
                            "description": (
                                'Required. The hypothesis or causal statement '
                                'to verify (for example "mutex hold blocks '
                                'Low[266]").'
                            ),
                        },
                        "claim_type": {"type": "string"},
                        "subject": {"type": "string"},
                        "object": {"type": "string"},
                        "evidence": {
                            "type": "array",
                            "items": {"type": ["string", "number"]},
                            "description": (
                                "Optional jump:TIME values in trace_time_unit."
                            ),
                        },
                    },
                    "required": ["claim"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": AI_TOOL_CHALLENGE_CONCLUSION,
                "description": (
                    "List alternative mechanisms and missing evidence for a "
                    "conclusion. Pass conclusion as a non-empty string when "
                    "possible."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "conclusion": {
                            "type": "string",
                            "description": (
                                "The conclusion or claim to challenge."
                            ),
                        },
                    },
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": AI_TOOL_INVESTIGATION_MEMORY,
                "description": (
                    "Store or recall similar past investigations "
                    "(Desktop [ai] investigation_memory / Web localStorage)."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "action": {
                            "type": "string",
                            "enum": ["recall", "store", "save", "add"],
                        },
                        "record": {"type": "object"},
                        "limit": {"type": "integer"},
                    },
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": AI_TOOL_CLUSTER_INCIDENTS,
                "description": "Cluster findings into incidents by time proximity.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "window_ns": {
                            "type": "number",
                            "description": (
                                "Clustering half-window in nanoseconds (_ns)."
                            ),
                        },
                    },
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": AI_TOOL_CLOSE_INVESTIGATION,
                "description": "Close the investigation with a conclusion and confidence.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "conclusion": {"type": "string"},
                        "confidence": {
                            "type": "string",
                            "enum": ["high", "medium", "low"],
                            "description": "Confidence band: high | medium | low.",
                        },
                    },
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": AI_TOOL_ANALYZE_DISTRIBUTION,
                "description": (
                    "Percentiles (p50/p90/p95/p99/p99.9), stddev, CV, and "
                    "3-sigma outlier rate for BTF execution, blocking, "
                    "priority-inheritance, or tick samples; caller values; "
                    "or finding magnitudes."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "values": {
                            "type": "array",
                            "items": {"type": "number"},
                        },
                        "metric": {
                            "type": "string",
                            "enum": [
                                "auto",
                                "execution",
                                "blocking",
                                "priority_inheritance",
                                "tick",
                            ],
                        },
                        "task": {"type": "string"},
                    },
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": AI_TOOL_ANALYZE_PERIODICITY,
                "description": (
                    "Period and jitter for tick/STI/ISR/timer/task-release "
                    "timestamps: expected vs p50/p99/max, RMS and peak-to-peak, "
                    "and a kind (period drift / release jitter / "
                    "execution-time variation / scheduler interference)."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "times": {
                            "type": "array",
                            "items": {"type": "number"},
                        },
                        "expected": {"type": "number"},
                        "source": {
                            "type": "string",
                            "enum": ["auto", "tick", "sti", "isr", "timer", "release"],
                        },
                        "task": {"type": "string"},
                        "durations": {
                            "type": "array",
                            "items": {"type": "number"},
                        },
                    },
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": AI_TOOL_SUMMARIZE_INVESTIGATION_CONTEXT,
                "description": "Compact findings, hypotheses, tools, and conclusion.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "conclusion": {"type": "string"},
                        "tools_run": {
                            "type": "array",
                            "items": {"type": "string"},
                        },
                    },
                },
            },
        },
    ])


def parse_tool_arguments(raw: Any) -> Dict[str, Any]:
    """Parse a tool ``arguments`` field (JSON string or already a dict)."""
    if raw is None:
        return {}
    if isinstance(raw, dict):
        return dict(raw)
    text = str(raw).strip()
    if not text:
        return {}
    try:
        data = json.loads(text)
    except (TypeError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def message_content_text(content: Any) -> str:
    """Flatten OpenAI / Gemini ``content`` (string or parts list) to text."""
    if content is None:
        return ""
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        parts: List[str] = []
        for item in content:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict):
                if item.get("type") in ("text", "output_text", None) or "text" in item:
                    parts.append(str(item.get("text") or item.get("content") or ""))
        return "\n".join(p for p in parts if p).strip()
    return str(content).strip()


def assistant_message_text(message: Any = None, choice: Any = None) -> str:
    """Best-effort text from an OpenAI-compatible assistant choice."""
    msg = message if isinstance(message, dict) else {}
    choice0 = choice if isinstance(choice, dict) else {}
    for src in (
        msg.get("content"),
        msg.get("refusal"),
        msg.get("reasoning_content"),
        msg.get("reasoning"),
        choice0.get("text"),
        choice0.get("content"),
    ):
        text = message_content_text(src)
        if text:
            return text
    return ""


def _choice_finish_reason(choice: Any) -> str:
    if not isinstance(choice, dict):
        return ""
    for key in ("finish_reason", "finishReason"):
        val = choice.get(key)
        if val is not None and str(val).strip():
            return str(val).strip().lower()
    return ""


def _choice0_from_chat_body(body: Any) -> Dict[str, Any]:
    if isinstance(body, dict):
        choices = body.get("choices")
        if isinstance(choices, list) and choices and isinstance(choices[0], dict):
            return choices[0]
    return {}


def is_malformed_function_call_finish(body: Any) -> bool:
    """True when Gemini filtered a tool call and returned no usable message."""
    reason = _choice_finish_reason(_choice0_from_chat_body(body))
    compact = reason.replace("_", "").replace("-", "").replace(" ", "")
    return "malformedfunction" in compact or "functioncallfilter" in compact


AI_MALFORMED_FUNCTION_CALL_NUDGE = (
    "Your last function call was rejected as malformed. "
    "Answer in plain text now. Do not call tools."
)


def _usage_completion_tokens(body: Any) -> int:
    if not isinstance(body, dict):
        return -1
    usage = body.get("usage")
    if not isinstance(usage, dict):
        return -1
    for key in ("completion_tokens", "completionTokens", "output_tokens"):
        if key not in usage:
            continue
        try:
            return int(usage[key])
        except (TypeError, ValueError):
            continue
    return -1


def empty_chat_completion_error(body: Any, *, had_tools: bool = False) -> str:
    """Human-readable error when a chat reply has no text and no tool calls.

    Avoid snake_case tokens that Markdown italicizes (``finish_reason`` →
    ``finishreason``) when the AI log renders the message.
    """
    choice0 = _choice0_from_chat_body(body)
    reason = _choice_finish_reason(choice0) or "unknown"
    tokens = _usage_completion_tokens(body)
    model = ""
    if isinstance(body, dict):
        model = str(body.get("model") or "").strip()
    model_bit = f" model={model}" if model else ""
    token_bit = f" completion tokens={tokens}" if tokens >= 0 else ""

    if reason in ("content_filter", "safety"):
        return (
            "The provider blocked the reply (safety / content filter)."
            f"{model_bit}"
        )

    tips = [
        "The model returned an empty assistant message "
        f"(finish reason={reason}{token_bit}{model_bit}).",
        "This is a known Gemini OpenAI-compat quirk with large prompts or tool calls.",
        "Retry, switch to a fuller model (for example gemini-2.5-flash), "
        "or narrow the Statistics scope.",
    ]
    if had_tools:
        tips.append(
            "Agent templates send tools; a plain Ask without tools may work "
            "when a lite model stalls."
        )
    return " ".join(tips)


def is_empty_assistant_message_error(msg: Any) -> bool:
    """True when the chat client failed because the model wrote nothing."""
    return "empty assistant message" in str(msg or "").lower()


# Gemini 3 OpenAI-compat requires thought_signature on the first functionCall
# of each step. Echo the real blob; use this dummy only when the call was not
# produced by Gemini (https://ai.google.dev/gemini-api/docs/thought-signatures).
GEMINI_SKIP_THOUGHT_SIGNATURE = "skip_thought_signature_validator"


def thought_signature_from_obj(obj: Any) -> str:
    """Read a Gemini thought signature from a tool_call / message / part."""
    if not isinstance(obj, dict):
        return ""
    for key in ("thought_signature", "thoughtSignature"):
        val = obj.get(key)
        if isinstance(val, str) and val.strip():
            return val.strip()
    extra = obj.get("extra_content")
    if isinstance(extra, dict):
        google = extra.get("google") if isinstance(extra.get("google"), dict) else {}
        for src in (google, extra):
            for key in ("thought_signature", "thoughtSignature"):
                val = src.get(key)
                if isinstance(val, str) and val.strip():
                    return val.strip()
    fn = obj.get("function")
    if isinstance(fn, dict):
        for key in ("thought_signature", "thoughtSignature"):
            val = fn.get(key)
            if isinstance(val, str) and val.strip():
                return val.strip()
    return ""


def gemini_thought_extra_content(signature: str) -> Dict[str, Any]:
    return {"google": {"thought_signature": str(signature)}}


def attach_thought_signature(call: Dict[str, Any], signature: str) -> Dict[str, Any]:
    """Set ``extra_content.google.thought_signature`` on an OpenAI-shaped call."""
    sig = str(signature or "").strip()
    if not sig:
        return call
    extra = call.get("extra_content")
    extra = dict(extra) if isinstance(extra, dict) else {}
    google = extra.get("google")
    google = dict(google) if isinstance(google, dict) else {}
    google["thought_signature"] = sig
    extra["google"] = google
    call["extra_content"] = extra
    return call


def needs_gemini_thought_signatures(
    *,
    base_url: str = "",
    model: str = "",
    preset: str = "",
) -> bool:
    """True for Gemini OpenAI-compat hosts / the Gemini preset."""
    del model  # model id alone is not enough (Ollama can serve gemini-* names)
    blob = f"{base_url} {preset}".lower()
    return "generativelanguage" in blob or "gemini" in blob


def ensure_gemini_thought_signatures(
    messages: Sequence[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """First function call in each assistant step must carry a thought_signature."""
    out: List[Dict[str, Any]] = []
    for msg in messages or []:
        if not isinstance(msg, dict):
            continue
        if str(msg.get("role") or "") != "assistant":
            out.append(msg)
            continue
        calls = msg.get("tool_calls")
        if not isinstance(calls, list) or not calls:
            out.append(msg)
            continue
        copied = dict(msg)
        new_calls: List[Any] = []
        for i, call in enumerate(calls):
            if not isinstance(call, dict):
                new_calls.append(call)
                continue
            c = dict(call)
            fn = c.get("function")
            if isinstance(fn, dict):
                c["function"] = dict(fn)
            sig = thought_signature_from_obj(c)
            if i == 0 and not sig:
                sig = GEMINI_SKIP_THOUGHT_SIGNATURE
            if sig:
                attach_thought_signature(c, sig)
            new_calls.append(c)
        copied["tool_calls"] = new_calls
        out.append(copied)
    return out


def _tool_call_name(obj: Any) -> str:
    """Function name from OpenAI / Gemini OpenAI-compat / extra_content shapes."""
    if not isinstance(obj, dict):
        return ""
    fn = obj.get("function") if isinstance(obj.get("function"), dict) else {}
    name = str(fn.get("name") or obj.get("name") or obj.get("tool") or "").strip()
    if name:
        return name
    for key in ("function_call", "functionCall"):
        nested = obj.get(key)
        if isinstance(nested, dict):
            name = str(nested.get("name") or "").strip()
            if name:
                return name
    extra = obj.get("extra_content")
    if isinstance(extra, dict):
        google = extra.get("google") if isinstance(extra.get("google"), dict) else {}
        for src in (google, extra):
            for key in ("function_call", "functionCall"):
                nested = src.get(key)
                if isinstance(nested, dict):
                    name = str(nested.get("name") or "").strip()
                    if name:
                        return name
            name = str(src.get("name") or "").strip()
            if name:
                return name
    return ""


def _tool_call_id(obj: Any, index: int) -> str:
    """Non-empty tool_call id. Gemini rejects follow-ups that echo ``id: ''``."""
    if not isinstance(obj, dict):
        return f"call_{index}"
    cid = str(obj.get("id") or "").strip()
    return cid or f"call_{index}"


def _extracted_tool_call(
    *,
    cid: str,
    name: str,
    arguments: Dict[str, Any],
    signature: str = "",
) -> Dict[str, Any]:
    item: Dict[str, Any] = {"id": cid, "name": name, "arguments": arguments}
    if signature:
        item["thought_signature"] = signature
    return item


def extract_tool_calls(message: Optional[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Normalise OpenAI / Ollama / Gemini / legacy function_call invocations."""
    if not isinstance(message, dict):
        return []
    out: List[Dict[str, Any]] = []
    calls = message.get("tool_calls")
    if isinstance(calls, str):
        try:
            calls = json.loads(calls)
        except (TypeError, ValueError):
            calls = []
    if isinstance(calls, list):
        for i, call in enumerate(calls):
            if not isinstance(call, dict):
                continue
            fn = call.get("function") if isinstance(call.get("function"), dict) else {}
            name = _tool_call_name(call)
            if not name:
                continue
            args = parse_tool_arguments(
                fn.get("arguments",
                       call.get("arguments", call.get("args", call.get("input"))))
            )
            out.append(_extracted_tool_call(
                cid=_tool_call_id(call, i),
                name=name,
                arguments=args,
                signature=thought_signature_from_obj(call),
            ))
    legacy = message.get("function_call")
    if isinstance(legacy, dict) and legacy.get("name"):
        out.append(_extracted_tool_call(
            cid=str(legacy.get("id") or "call_0"),
            name=str(legacy["name"]).strip(),
            arguments=parse_tool_arguments(legacy.get("arguments")),
            signature=thought_signature_from_obj(legacy),
        ))
    # Anthropic-style / Gemini parts mixed into content.
    content = message.get("content")
    if isinstance(content, list):
        for i, part in enumerate(content):
            if not isinstance(part, dict):
                continue
            ptype = str(part.get("type") or "")
            nested = part.get("functionCall") if isinstance(
                part.get("functionCall"), dict) else (
                part.get("function_call") if isinstance(
                    part.get("function_call"), dict) else None
            )
            if (
                ptype not in (
                    "tool_use", "function_call", "tool_call", "functionCall")
                and not (isinstance(nested, dict) and nested.get("name"))
            ):
                continue
            name = _tool_call_name(part)
            if not name:
                continue
            nested_args = nested if isinstance(nested, dict) else {}
            args = parse_tool_arguments(
                part.get("input", part.get("arguments", part.get("args",
                    nested_args.get("args", nested_args.get("arguments"))))))
            out.append(_extracted_tool_call(
                cid=str(part.get("id") or "").strip() or f"part_{i}",
                name=name,
                arguments=args,
                signature=thought_signature_from_obj(part),
            ))
    if out and not str(out[0].get("thought_signature") or "").strip():
        fallback = thought_signature_from_obj(message)
        if not fallback and isinstance(content, list):
            for part in content:
                fallback = thought_signature_from_obj(part)
                if fallback:
                    break
        if fallback:
            out[0]["thought_signature"] = fallback
    return out


_BTFTOOL_FENCE_RE = re.compile(
    r"```(?:btftool|tool_call|tool-call)\s*\n(.*?)```",
    re.DOTALL | re.IGNORECASE,
)
_XML_TOOL_RE = re.compile(
    r"<tool_call>\s*(.*?)\s*</tool_call>",
    re.DOTALL | re.IGNORECASE,
)


def _loads_json_values(body: str) -> List[Any]:
    """Parse one JSON value, a JSON array, or several concatenated/NDJSON values."""
    src = (body or "").strip()
    if not src:
        return []
    try:
        return [json.loads(src)]
    except (TypeError, ValueError):
        pass
    decoder = json.JSONDecoder()
    out: List[Any] = []
    idx = 0
    n = len(src)
    while idx < n:
        while idx < n and src[idx].isspace():
            idx += 1
        if idx >= n:
            break
        try:
            val, end = decoder.raw_decode(src, idx)
        except ValueError:
            break
        out.append(val)
        idx = end
    return out


def _tool_call_from_obj(obj: Any, idx: int) -> Optional[Dict[str, Any]]:
    if not isinstance(obj, dict):
        return None
    name = str(obj.get("name") or obj.get("tool") or "").strip()
    fn = obj.get("function") if isinstance(obj.get("function"), dict) else {}
    if fn:
        name = name or str(fn.get("name") or "").strip()
        args = parse_tool_arguments(fn.get("arguments", obj.get("arguments")))
    else:
        args = obj.get("arguments") or obj.get("parameters") or obj.get("args")
        if not isinstance(args, dict):
            args = parse_tool_arguments(args)
        if not args:
            args = {
                k: v for k, v in obj.items()
                if k not in ("name", "tool", "function", "id", "type")
            }
    if name not in AI_VIEWER_TOOL_NAMES:
        return None
    ok, err = validate_tool_call(name, args)
    if err:
        return None
    return {"id": f"text_{idx}", "name": name, "arguments": ok or args}


def parse_tool_calls_from_text(text: str) -> List[Dict[str, Any]]:
    """Parse ```btftool fences and <tool_call> blobs (models without native tools)."""
    out: List[Dict[str, Any]] = []
    seen = set()

    def _add(obj: Any) -> None:
        call = _tool_call_from_obj(obj, len(out))
        if not call:
            return
        key = (call["name"], json.dumps(call["arguments"], sort_keys=True, default=str))
        if key in seen:
            return
        seen.add(key)
        out.append(call)

    src = text or ""
    for m in _BTFTOOL_FENCE_RE.finditer(src):
        body = (m.group(1) or "").strip()
        for data in _loads_json_values(body):
            if isinstance(data, list):
                for item in data:
                    _add(item)
            else:
                _add(data)
    for m in _XML_TOOL_RE.finditer(src):
        body = (m.group(1) or "").strip()
        try:
            _add(json.loads(body))
            continue
        except (TypeError, ValueError):
            pass
        lines = body.split("\n", 1)
        if len(lines) == 2:
            try:
                _add({"name": lines[0].strip(), "arguments": json.loads(lines[1])})
            except (TypeError, ValueError):
                pass
    return out


def merge_tool_calls(
    structured: Sequence[Dict[str, Any]],
    from_text: Sequence[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """Prefer native tool_calls; append unique text-parsed calls."""
    out: List[Dict[str, Any]] = []
    seen = set()
    for call in list(structured or []) + list(from_text or []):
        if not isinstance(call, dict) or not call.get("name"):
            continue
        key = (
            str(call.get("name")),
            json.dumps(call.get("arguments") or {}, sort_keys=True, default=str),
        )
        if key in seen:
            continue
        seen.add(key)
        out.append(dict(call))
    return out


def strip_parsed_tool_markup(text: str) -> str:
    """Remove btftool fences / XML after they were turned into GUI cards."""
    out = _BTFTOOL_FENCE_RE.sub("", text or "")
    out = _XML_TOOL_RE.sub("", out)
    return re.sub(r"\n{3,}", "\n\n", out).strip()


def _as_float_list(value: Any) -> List[float]:
    if not isinstance(value, (list, tuple)):
        return []
    out: List[float] = []
    for item in value:
        n = _as_scalar_float(item)
        if n is not None:
            out.append(n)
    return out


def _as_scalar_float(value: Any) -> Optional[float]:
    """Coerce a tool arg to float, matching JS ``Number(x)`` for common LLM shapes.

    Accepts ints/floats, numeric strings, and single-element arrays
    (``[3087194]`` → ``3087194.0``). Rejects bools, multi-element arrays,
    objects, and non-numeric strings. Keep in sync with
    ``web/src/utils/aiTools.js`` ``asScalarNumber``.
    """
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        try:
            n = float(value)
        except (TypeError, ValueError, OverflowError):
            return None
        if n != n:  # NaN
            return None
        return n
    if isinstance(value, (list, tuple)):
        if len(value) != 1:
            return None
        return _as_scalar_float(value[0])
    if isinstance(value, str):
        s = value.strip()
        if not s:
            return None
        try:
            n = float(s)
        except (TypeError, ValueError):
            return None
        if n != n:
            return None
        return n
    return None


def _normalize_confidence_band(value: Any) -> str:
    """Map confidence args to ``high|medium|low`` (empty if omitted/unknown)."""
    raw = str(value or "").strip().lower().replace("-", " ").replace("_", " ")
    if not raw:
        return ""
    if raw in ("high", "h"):
        return "high"
    if raw in ("medium", "med", "m", "mid"):
        return "medium"
    if raw in ("low", "l"):
        return "low"
    # Title-case prose from the model
    if "high" in raw:
        return "high"
    if "medium" in raw or "med" in raw:
        return "medium"
    if "low" in raw:
        return "low"
    return ""


def coerce_claim_text(args: Any = None) -> str:
    """Coerce verify_claim / challenge_conclusion text from common model aliases.

    Small local models often omit ``claim`` and send hypothesis/statement/etc.
    """
    a = args if isinstance(args, dict) else {}
    for key in (
        "claim", "statement", "hypothesis", "conclusion", "text", "assertion",
        "finding", "summary", "message", "query", "description",
    ):
        v = str(a.get(key) or "").strip()
        if v:
            return v
    subject = str(a.get("subject") or "").strip()
    obj = str(a.get("object") or a.get("target") or "").strip()
    if subject and obj:
        return f"{subject} causes {obj}"
    if subject:
        return subject
    if obj:
        return obj
    return ""


def _fmt_trace_num(value: Any) -> str:
    n = _as_scalar_float(value)
    if n is None:
        return str(value)
    if n.is_integer():
        return str(int(n))
    return f"{n:g}"


def normalize_raw_metric(name: Any) -> str:
    """Map a metric alias onto one of ``AI_RAW_METRIC_NAMES`` (empty if unknown)."""
    want = str(name or "").strip().lower().replace("-", "_").replace(" ", "_")
    return _RAW_METRIC_ALIASES.get(want, "")


def is_query_tool(name: str) -> bool:
    return str(name or "") in (
        AI_TOOL_QUERY_RAW_METRIC,
        AI_TOOL_SEARCH_TIMELINE,
        AI_TOOL_TRIGGER_COMPARE,
        AI_TOOL_INVESTIGATE,
        AI_TOOL_DETECT_ANOMALIES,
        AI_TOOL_CORRELATE_EVENTS,
        AI_TOOL_FIND_CRITICAL_PATH,
        AI_TOOL_COMPARE_PERFORMANCE,
        AI_TOOL_GENERATE_REPORT,
        AI_TOOL_CHECK_BUDGET,
        AI_TOOL_OPTIMIZE,
        AI_TOOL_REGRESSION_EXPLAIN,
        AI_TOOL_INVESTIGATION_REPLAY,
        AI_TOOL_WHAT_IF,
        AI_TOOL_OPTIMIZE_EXPERIMENT,
        AI_TOOL_ANALYZE_TRACES,
        AI_TOOL_BASELINE_SCORE,
        AI_TOOL_RECOMMEND_EXPERIMENTS,
        AI_TOOL_DETECT_PRIORITY_INVERSION,
        AI_TOOL_FIND_RELATED_FINDINGS,
        AI_TOOL_COMPARE_TASKS,
        AI_TOOL_EXPLAIN_FINDING,
        AI_TOOL_INTERPRET_QUERY,
        AI_TOOL_VALIDATE_EXPERIMENT,
        AI_TOOL_MANAGE_HYPOTHESES,
        AI_TOOL_PLAN_INVESTIGATION,
        AI_TOOL_SUGGEST_SCOPE,
        AI_TOOL_DETECT_CONTRADICTIONS,
        AI_TOOL_ASSESS_EVIDENCE_SUFFICIENCY,
        AI_TOOL_CLUSTER_FINDINGS,
        AI_TOOL_GENERATE_FINGERPRINT,
        AI_TOOL_FIND_SIMILAR_INVESTIGATIONS,
        AI_TOOL_REGRESSION_LOCALIZE,
        AI_TOOL_BUILD_CAUSAL_CHAIN,
        AI_TOOL_GENERATE_EXPERIMENT_PLAN,
        AI_TOOL_RECORD_EXPERIMENT_OUTCOME,
        AI_TOOL_SCORE_INVESTIGATION,
        AI_TOOL_ANALYZE_TEMPORAL_CAUSALITY,
        AI_TOOL_BUILD_TASK_DEPENDENCY_GRAPH,
        AI_TOOL_DECOMPOSE_RESPONSE_TIME,
        AI_TOOL_RANK_ROOT_CAUSES,
        AI_TOOL_VERIFY_CLAIM,
        AI_TOOL_CHALLENGE_CONCLUSION,
        AI_TOOL_INVESTIGATION_MEMORY,
        AI_TOOL_CLUSTER_INCIDENTS,
        AI_TOOL_CLOSE_INVESTIGATION,
        AI_TOOL_ANALYZE_DISTRIBUTION,
        AI_TOOL_ANALYZE_PERIODICITY,
        AI_TOOL_SUMMARIZE_INVESTIGATION_CONTEXT,
    )


def is_export_tool(name: str) -> bool:
    return str(name or "") in (AI_TOOL_EXPORT_REPORT, AI_TOOL_EXPORT_INVESTIGATION)


def tool_mutates_gui(name: str) -> bool:
    """True when applying the tool changes timeline / inspector state."""
    return str(name or "") in (
        AI_TOOL_SET_CURSORS,
        AI_TOOL_ZOOM_TO_RANGE,
        AI_TOOL_HIGHLIGHT_TASK,
        AI_TOOL_SET_VIEW_MODE,
        AI_TOOL_OPEN_CORRIDOR,
        AI_TOOL_ADD_ANNOTATION,
        AI_TOOL_BOOKMARK_FINDING,
        AI_TOOL_CLEAR_MARKS,
        AI_TOOL_RESET_VIEW,
    )


def is_navigation_tool(name: str) -> bool:
    """True for focus/zoom/highlight tools (navigation-only)."""
    return str(name or "") in (
        AI_TOOL_SET_CURSORS,
        AI_TOOL_ZOOM_TO_RANGE,
        AI_TOOL_HIGHLIGHT_TASK,
    )


# Apply-card action classes. Keep labels stable for Desktop/Web lockstep.
VIEWER_TOOL_ACTION_NAVIGATION = "Navigation"
VIEWER_TOOL_ACTION_SCOPE = "Scope"
VIEWER_TOOL_ACTION_FILTER = "Filter"
VIEWER_TOOL_ACTION_ANNOTATION = "Annotation"
VIEWER_TOOL_ACTION_EXPORT = "Export"
VIEWER_TOOL_ACTION_CALCULATION = "Calculation"

VIEWER_TOOL_ACTION_CLASSES: Tuple[str, ...] = (
    VIEWER_TOOL_ACTION_NAVIGATION,
    VIEWER_TOOL_ACTION_SCOPE,
    VIEWER_TOOL_ACTION_FILTER,
    VIEWER_TOOL_ACTION_ANNOTATION,
    VIEWER_TOOL_ACTION_EXPORT,
    VIEWER_TOOL_ACTION_CALCULATION,
)


def classify_viewer_tool(name: str) -> str:
    """Classify a tool for Apply-card labels."""
    n = str(name or "")
    if is_navigation_tool(n) or n in (
        AI_TOOL_SET_VIEW_MODE,
        AI_TOOL_OPEN_CORRIDOR,
        AI_TOOL_RESET_VIEW,
        AI_TOOL_SEARCH_TIMELINE,
        AI_TOOL_TRIGGER_COMPARE,
    ):
        return VIEWER_TOOL_ACTION_NAVIGATION
    if n == AI_TOOL_SUGGEST_SCOPE:
        return VIEWER_TOOL_ACTION_SCOPE
    if n in (
        AI_TOOL_ADD_ANNOTATION,
        AI_TOOL_BOOKMARK_FINDING,
        AI_TOOL_CLEAR_MARKS,
    ):
        return VIEWER_TOOL_ACTION_ANNOTATION
    if is_export_tool(n):
        return VIEWER_TOOL_ACTION_EXPORT
    return VIEWER_TOOL_ACTION_CALCULATION


def format_tool_action_label(name: str, args: Optional[Dict[str, Any]] = None) -> str:
    """``[Navigation] Set cursors at […]`` for Apply cards and history."""
    kind = classify_viewer_tool(name)
    return f"[{kind}] {summarise_tool_call(name, args)}"


def tool_batch_auto_runs(tools: Optional[Sequence[Any]]) -> bool:
    """Query/export/navigation-only batches run immediately (no Apply card)."""
    names = [str((t or {}).get("name") or "") for t in (tools or [])]
    return bool(names) and all(
        is_query_tool(n) or is_export_tool(n) or is_navigation_tool(n)
        for n in names
    )


def validate_tool_call(name: str, args: Optional[Dict[str, Any]]) -> Tuple[Optional[Dict[str, Any]], str]:
    """Return ``(normalised_args, error)``. error is empty on success."""
    a = dict(args or {})
    if name == AI_TOOL_SET_CURSORS:
        times = _as_float_list(a.get("timestamps"))
        if not times:
            return None, "timestamps must be a non-empty number array"
        times = times[:_MAX_CURSORS_TOOL]
        return {"timestamps": times}, ""
    if name == AI_TOOL_ZOOM_TO_RANGE:
        lo = _as_scalar_float(a.get("start_time"))
        hi = _as_scalar_float(a.get("end_time"))
        if lo is None or hi is None:
            return None, "start_time and end_time must be numbers"
        if hi == lo:
            return None, "start_time and end_time must differ"
        if hi < lo:
            lo, hi = hi, lo
        return {"start_time": lo, "end_time": hi}, ""
    if name == AI_TOOL_HIGHLIGHT_TASK:
        key = str(a.get("task_name_or_id") or "").strip()
        return {"task_name_or_id": key}, ""
    if name == AI_TOOL_SET_VIEW_MODE:
        mode = str(a.get("mode") or "").strip().lower()
        if mode not in ("task", "core"):
            return None, 'mode must be "task" or "core"'
        ori_raw = a.get("orientation")
        ori = None
        if ori_raw not in (None, ""):
            ori = str(ori_raw).strip().lower()
            if ori in ("h", "horiz"):
                ori = "horizontal"
            if ori in ("v", "vert"):
                ori = "vertical"
            if ori not in ("horizontal", "vertical"):
                return None, 'orientation must be "horizontal" or "vertical"'
        out: Dict[str, Any] = {"mode": mode}
        if ori:
            out["orientation"] = ori
        return out, ""
    if name == AI_TOOL_OPEN_CORRIDOR:
        src = str(a.get("core_from") or "").strip()
        dst = str(a.get("core_to") or "").strip()
        return {"core_from": src, "core_to": dst}, ""
    if name == AI_TOOL_ADD_ANNOTATION:
        t = _as_scalar_float(a.get("time"))
        if t is None:
            return None, "time must be a number"
        note = str(a.get("note") or "").strip()
        if not note:
            return None, "note must be a non-empty string"
        if len(note) > _MAX_ANNOTATION_NOTE:
            note = note[:_MAX_ANNOTATION_NOTE].rstrip()
        return {"time": t, "note": note}, ""
    if name == AI_TOOL_QUERY_RAW_METRIC:
        task = str(a.get("task") or "").strip()
        if not task:
            return None, "task must be a non-empty string"
        metric = normalize_raw_metric(a.get("metric"))
        if not metric:
            return None, (
                "metric must be one of: " + ", ".join(AI_RAW_METRIC_NAMES)
            )
        return {"task": task, "metric": metric}, ""
    if name == AI_TOOL_EXPORT_REPORT:
        fmt = str(a.get("format") or "html").strip().lower()
        if fmt in ("htm", "html"):
            fmt = "html"
        elif fmt == "csv":
            fmt = "csv"
        elif fmt == "json":
            fmt = "json"
        else:
            return None, 'format must be "html", "csv", or "json"'
        mode = str(a.get("mode") or a.get("report_mode") or "summary").strip().lower()
        if mode not in ("summary", "technical", "full"):
            mode = "summary"
        return {"format": fmt, "mode": mode}, ""
    if name == AI_TOOL_CLEAR_MARKS:
        what = str(a.get("what") or "all").strip().lower()
        aliases = {
            "annotation": "annotations",
            "cursor": "cursors",
            "bookmark": "bookmarks",
            "marks": "all",
            "both": "all",
        }
        what = aliases.get(what, what)
        if what not in AI_CLEAR_MARKS_TARGETS:
            return None, (
                "what must be one of: " + ", ".join(AI_CLEAR_MARKS_TARGETS)
            )
        return {"what": what}, ""
    if name == AI_TOOL_RESET_VIEW:
        return {}, ""
    if name == AI_TOOL_SEARCH_TIMELINE:
        query = str(a.get("query") or "").strip()
        if not query:
            return None, "query must be a non-empty string"
        mode = str(a.get("mode") or "contains").strip().lower()
        if mode == "tag":
            mode = "tags"
        if mode not in AI_FIND_MODES:
            return None, "mode must be one of: " + ", ".join(AI_FIND_MODES)
        return {"query": query, "mode": mode}, ""
    if name == AI_TOOL_TRIGGER_COMPARE:
        return {
            "tab_a": str(a.get("tab_a") if a.get("tab_a") is not None else "").strip(),
            "tab_b": str(a.get("tab_b") if a.get("tab_b") is not None else "").strip(),
        }, ""
    if name == AI_TOOL_INVESTIGATE:
        depth_raw = a.get("depth", 2)
        try:
            depth = int(depth_raw)
        except (TypeError, ValueError):
            return None, "depth must be an integer 1–5"
        depth = max(1, min(5, depth))
        return {
            "finding_id": str(a.get("finding_id") or "").strip(),
            "depth": depth,
        }, ""
    if name == AI_TOOL_DETECT_ANOMALIES:
        lim_raw = a.get("limit", 10)
        try:
            limit = int(lim_raw)
        except (TypeError, ValueError):
            return None, "limit must be an integer 1–40"
        return {"limit": max(1, min(40, limit))}, ""
    if name == AI_TOOL_CORRELATE_EVENTS:
        task = str(a.get("task") or "").strip()
        if not task:
            return None, "task must be a non-empty string"
        out: Dict[str, Any] = {"task": task, "around_time": None, "window": 0.0}
        if a.get("around_time") is not None and str(a.get("around_time")).strip() != "":
            t = _as_scalar_float(a.get("around_time"))
            if t is None:
                return None, "around_time must be a number"
            out["around_time"] = t
        if a.get("window") is not None and str(a.get("window")).strip() != "":
            w = _as_scalar_float(a.get("window"))
            if w is None:
                return None, "window must be a number"
            out["window"] = max(0.0, w)
        return out, ""
    if name == AI_TOOL_FIND_CRITICAL_PATH:
        task = str(a.get("task") or "").strip()
        if not task:
            return None, "task must be a non-empty string"
        out: Dict[str, Any] = {"task": task, "timestamp": None, "window": 2000.0}
        if a.get("timestamp") is not None and str(a.get("timestamp")).strip() != "":
            t = _as_scalar_float(a.get("timestamp"))
            if t is None:
                return None, "timestamp must be a number"
            out["timestamp"] = t
        if a.get("window") is not None and str(a.get("window")).strip() != "":
            w = _as_scalar_float(a.get("window"))
            if w is None:
                return None, "window must be a number"
            out["window"] = max(0.0, w)
        return out, ""
    if name == AI_TOOL_COMPARE_PERFORMANCE:
        return {
            "tab_a": str(a.get("tab_a") if a.get("tab_a") is not None else "").strip(),
            "tab_b": str(a.get("tab_b") if a.get("tab_b") is not None else "").strip(),
        }, ""
    if name == AI_TOOL_GENERATE_REPORT:
        return {
            "report_type": str(a.get("report_type") or "performance").strip().lower()
            or "performance",
            "finding_id": str(a.get("finding_id") or "").strip(),
        }, ""
    if name == AI_TOOL_CHECK_BUDGET:
        budgets = a.get("budgets")
        if budgets is not None and not isinstance(budgets, dict):
            return None, "budgets must be an object"
        tasks = a.get("tasks")
        if tasks is not None and not isinstance(tasks, (list, tuple)):
            return None, "tasks must be an array"
        out: Dict[str, Any] = {}
        if isinstance(budgets, dict):
            out["budgets"] = budgets
        if isinstance(tasks, (list, tuple)):
            out["tasks"] = [t for t in tasks if isinstance(t, dict)]
        return out, ""
    if name == AI_TOOL_OPTIMIZE:
        lim_raw = a.get("limit", 5)
        try:
            limit = int(lim_raw)
        except (TypeError, ValueError):
            return None, "limit must be an integer 1–20"
        return {"limit": max(1, min(20, limit))}, ""
    if name == AI_TOOL_REGRESSION_EXPLAIN:
        return {
            "tab_a": str(a.get("tab_a") if a.get("tab_a") is not None else "").strip(),
            "tab_b": str(a.get("tab_b") if a.get("tab_b") is not None else "").strip(),
        }, ""
    if name == AI_TOOL_BOOKMARK_FINDING:
        t = _as_scalar_float(a.get("time"))
        if t is None:
            return None, "time must be a number"
        kind = str(a.get("kind") or "").strip().lower().replace("-", "_").replace(" ", "_")
        if kind in ("root", "cause", "rca"):
            kind = "root_cause"
        if kind in ("corr", "related"):
            kind = "correlated"
        if kind in ("ok", "normal", "ref"):
            kind = "reference"
        if kind not in AI_BOOKMARK_KINDS:
            return None, (
                "kind must be one of: " + ", ".join(AI_BOOKMARK_KINDS)
            )
        note = str(a.get("note") or "").strip()
        if len(note) > _MAX_ANNOTATION_NOTE:
            note = note[:_MAX_ANNOTATION_NOTE].rstrip()
        return {"time": t, "kind": kind, "note": note}, ""
    if name == AI_TOOL_INVESTIGATION_REPLAY:
        tools_run = a.get("tools_run") or []
        if not isinstance(tools_run, (list, tuple)):
            return None, "tools_run must be an array of strings"
        evidence = a.get("evidence_times") or []
        if not isinstance(evidence, (list, tuple)):
            return None, "evidence_times must be an array of numbers"
        return {
            "finding_id": str(a.get("finding_id") or "").strip(),
            "conclusion": str(a.get("conclusion") or "").strip(),
            "tools_run": [str(t) for t in tools_run if t],
            "evidence_times": _as_float_list(list(evidence)),
        }, ""
    if name == AI_TOOL_WHAT_IF:
        change = str(a.get("change") or "").strip()
        task = str(
            a.get("task") or a.get("task_id") or a.get("task_name_or_id") or ""
        ).strip()
        # Models often pass only a task id after "run what_if on task 9".
        if not change and task:
            change = f"pin {task} to preferred core"
        if not change:
            return None, (
                "change must describe the experiment "
                "(e.g. pin CS[9] to Core_0), or pass task for a default pin"
            )
        return {
            "change": change,
            "task": task,
        }, ""
    if name == AI_TOOL_OPTIMIZE_EXPERIMENT:
        lim_raw = a.get("limit", 5)
        try:
            limit = int(lim_raw)
        except (TypeError, ValueError):
            return None, "limit must be an integer 1–12"
        return {
            "task": str(a.get("task") or "").strip(),
            "limit": max(1, min(12, limit)),
        }, ""
    if name == AI_TOOL_ANALYZE_TRACES:
        return {}, ""
    if name == AI_TOOL_BASELINE_SCORE:
        baseline = a.get("baseline")
        if baseline is not None and not isinstance(baseline, dict):
            return None, "baseline must be an object"
        snapshot = a.get("snapshot")
        if snapshot is not None and not isinstance(snapshot, dict):
            return None, "snapshot must be an object"
        out: Dict[str, Any] = {"task": str(a.get("task") or "").strip()}
        if isinstance(baseline, dict):
            out["baseline"] = baseline
        if isinstance(snapshot, dict):
            out["snapshot"] = snapshot
        return out, ""
    if name == AI_TOOL_RECOMMEND_EXPERIMENTS:
        lim_raw = a.get("limit", 5)
        try:
            limit = int(lim_raw)
        except (TypeError, ValueError):
            return None, "limit must be an integer 1–20"
        return {
            "finding_id": str(a.get("finding_id") or "").strip(),
            "task": str(a.get("task") or "").strip(),
            "limit": max(1, min(20, limit)),
        }, ""
    if name == AI_TOOL_EXPORT_INVESTIGATION:
        tools_run = a.get("tools_run") or []
        if not isinstance(tools_run, (list, tuple)):
            return None, "tools_run must be an array of strings"
        evidence = a.get("evidence_times") or []
        if not isinstance(evidence, (list, tuple)):
            return None, "evidence_times must be an array of numbers"
        return {
            "finding_id": str(a.get("finding_id") or "").strip(),
            "conclusion": str(a.get("conclusion") or "").strip(),
            "tools_run": [str(t) for t in tools_run if t],
            "evidence_times": _as_float_list(list(evidence)),
        }, ""
    if name == AI_TOOL_DETECT_PRIORITY_INVERSION:
        out: Dict[str, Any] = {"task": str(a.get("task") or "").strip(), "window": None}
        if a.get("window") is not None and str(a.get("window")).strip() != "":
            try:
                out["window"] = max(0.0, float(a.get("window")))
            except (TypeError, ValueError):
                return None, "window must be a number"
        return out, ""
    if name == AI_TOOL_FIND_RELATED_FINDINGS:
        lim_raw = a.get("limit", 10)
        try:
            limit = int(lim_raw)
        except (TypeError, ValueError):
            return None, "limit must be an integer 1–40"
        out = {
            "finding_id": str(a.get("finding_id") or "").strip(),
            "task": str(a.get("task") or "").strip(),
            "metric": str(a.get("metric") or "").strip().lower(),
            "window": None,
            "limit": max(1, min(40, limit)),
        }
        if a.get("window") is not None and str(a.get("window")).strip() != "":
            try:
                out["window"] = max(0.0, float(a.get("window")))
            except (TypeError, ValueError):
                return None, "window must be a number"
        return out, ""
    if name == AI_TOOL_COMPARE_TASKS:
        task_a = str(a.get("task_a") or "").strip()
        task_b = str(a.get("task_b") or "").strip()
        if not task_a or not task_b:
            return None, "task_a and task_b must be non-empty strings"
        metrics = a.get("metrics")
        if metrics is not None and not isinstance(metrics, (list, tuple)):
            return None, "metrics must be an array"
        out = {"task_a": task_a, "task_b": task_b}
        if isinstance(metrics, (list, tuple)):
            out["metrics"] = [str(m).strip().lower() for m in metrics if str(m or "").strip()]
        return out, ""
    if name == AI_TOOL_EXPLAIN_FINDING:
        level = str(a.get("level") or "technical").strip().lower() or "technical"
        if level not in ("quick", "technical", "deep"):
            return None, 'level must be "quick", "technical", or "deep"'
        return {
            "finding_id": str(a.get("finding_id") or "").strip(),
            "level": level,
        }, ""
    if name == AI_TOOL_INTERPRET_QUERY:
        q = str(a.get("question") or "").strip()
        if not q:
            return None, "question must be a non-empty string"
        return {"question": q}, ""
    if name == AI_TOOL_VALIDATE_EXPERIMENT:
        expected = a.get("expected") if isinstance(a.get("expected"), dict) else {}
        actual = a.get("actual") if isinstance(a.get("actual"), dict) else {}
        return {"expected": expected, "actual": actual}, ""
    if name == AI_TOOL_MANAGE_HYPOTHESES:
        hid = str(a.get("hypothesis_id") or "").strip()
        if not hid:
            return None, "hypothesis_id must be a non-empty string"
        status = str(a.get("status") or "").strip().lower()
        if status not in ("supported", "possible", "rejected", "need_evidence"):
            return None, "status must be supported|possible|rejected|need_evidence"
        return {
            "hypothesis_id": hid,
            "status": status,
            "reason": str(a.get("reason") or "").strip(),
            "finding_id": str(a.get("finding_id") or "").strip(),
        }, ""
    if name == AI_TOOL_PLAN_INVESTIGATION:
        return {
            "question": str(a.get("question") or "").strip(),
            "finding_id": str(a.get("finding_id") or "").strip(),
        }, ""
    if name == AI_TOOL_SUGGEST_SCOPE:
        return {"question": str(a.get("question") or "").strip()}, ""
    if name == AI_TOOL_DETECT_CONTRADICTIONS:
        metrics = a.get("metrics") if isinstance(a.get("metrics"), dict) else {}
        return {
            "hypothesis": str(a.get("hypothesis") or "").strip(),
            "metrics": metrics,
        }, ""
    if name == AI_TOOL_ASSESS_EVIDENCE_SUFFICIENCY:
        tools = a.get("tools_run")
        if tools is not None and not isinstance(tools, (list, tuple)):
            return None, "tools_run must be an array"
        return {
            "tools_run": [str(t) for t in (tools or [])],
        }, ""
    if name in (
        AI_TOOL_CLUSTER_FINDINGS,
        AI_TOOL_GENERATE_FINGERPRINT,
        AI_TOOL_BUILD_CAUSAL_CHAIN,
    ):
        return {}, ""
    if name == AI_TOOL_FIND_SIMILAR_INVESTIGATIONS:
        limit = a.get("limit", 5)
        try:
            limit = int(limit)
        except (TypeError, ValueError):
            return None, "limit must be an integer"
        return {"limit": limit}, ""
    if name == AI_TOOL_REGRESSION_LOCALIZE:
        return {
            "label_a": str(a.get("label_a") or "A").strip() or "A",
            "label_b": str(a.get("label_b") or "B").strip() or "B",
        }, ""
    if name == AI_TOOL_GENERATE_EXPERIMENT_PLAN:
        limit = a.get("limit", 3)
        try:
            limit = int(limit)
        except (TypeError, ValueError):
            limit = 3
        return {
            "task": str(a.get("task") or "").strip(),
            "limit": limit,
        }, ""
    if name == AI_TOOL_RECORD_EXPERIMENT_OUTCOME:
        return {
            "change": str(a.get("change") or "").strip(),
            "predicted": str(a.get("predicted") or "").strip(),
            "actual": str(a.get("actual") or "").strip(),
            "quality": str(a.get("quality") or "").strip(),
        }, ""
    if name == AI_TOOL_SCORE_INVESTIGATION:
        tools = a.get("tools_run")
        if tools is not None and not isinstance(tools, (list, tuple)):
            return None, "tools_run must be an array"
        elapsed = a.get("elapsed_s")
        if elapsed not in (None, ""):
            try:
                elapsed = float(elapsed)
            except (TypeError, ValueError):
                return None, "elapsed_s must be a number"
        else:
            elapsed = None
        return {
            "tools_run": [str(t) for t in (tools or [])],
            "conclusion": str(a.get("conclusion") or "").strip(),
            "confidence": _normalize_confidence_band(a.get("confidence")),
            "elapsed_s": elapsed,
        }, ""
    if name == AI_TOOL_ANALYZE_TEMPORAL_CAUSALITY:
        return {"task": str(a.get("task") or "").strip()}, ""
    if name == AI_TOOL_BUILD_TASK_DEPENDENCY_GRAPH:
        return {"task": str(a.get("task") or "").strip()}, ""
    if name == AI_TOOL_DECOMPOSE_RESPONSE_TIME:
        return {"task": str(a.get("task") or "").strip()}, ""
    if name == AI_TOOL_RANK_ROOT_CAUSES:
        return {}, ""
    if name == AI_TOOL_VERIFY_CLAIM:
        claim = coerce_claim_text(a)
        if not claim:
            return None, "claim must be a non-empty string"
        ev = a.get("evidence")
        if ev is not None and not isinstance(ev, (list, tuple)):
            return None, "evidence must be an array"
        return {
            "claim": claim,
            "claim_type": str(a.get("claim_type") or "causal").strip() or "causal",
            "subject": str(a.get("subject") or "").strip(),
            "object": str(a.get("object") or "").strip(),
            "evidence": list(ev or []),
        }, ""
    if name == AI_TOOL_CHALLENGE_CONCLUSION:
        return {
            "conclusion": coerce_claim_text(a) or str(a.get("conclusion") or "").strip(),
        }, ""
    if name == AI_TOOL_INVESTIGATION_MEMORY:
        rec = a.get("record") if isinstance(a.get("record"), dict) else None
        limit = a.get("limit", 5)
        try:
            limit = int(limit)
        except (TypeError, ValueError):
            return None, "limit must be an integer"
        return {
            "action": str(a.get("action") or "recall").strip() or "recall",
            "record": rec,
            "limit": limit,
        }, ""
    if name == AI_TOOL_CLUSTER_INCIDENTS:
        win = a.get("window_ns", 1e6)
        try:
            win = float(win)
        except (TypeError, ValueError):
            return None, "window_ns must be a number"
        return {"window_ns": win}, ""
    if name == AI_TOOL_CLOSE_INVESTIGATION:
        return {
            "conclusion": str(a.get("conclusion") or "").strip(),
            "confidence": _normalize_confidence_band(a.get("confidence")),
        }, ""
    if name == AI_TOOL_ANALYZE_DISTRIBUTION:
        vals = a.get("values")
        if vals is not None and not isinstance(vals, (list, tuple)):
            return None, "values must be an array"
        return {
            "values": list(vals or []),
            "metric": str(a.get("metric") or "").strip(),
            "task": str(a.get("task") or "").strip(),
        }, ""
    if name == AI_TOOL_ANALYZE_PERIODICITY:
        times = a.get("times")
        if times is not None and not isinstance(times, (list, tuple)):
            return None, "times must be an array"
        durs = a.get("durations")
        if durs is not None and not isinstance(durs, (list, tuple)):
            return None, "durations must be an array"
        expected = a.get("expected")
        if expected not in (None, ""):
            try:
                expected = float(expected)
            except (TypeError, ValueError):
                return None, "expected must be a number"
        else:
            expected = None
        src = str(a.get("source") or "auto").strip().lower() or "auto"
        if src not in ("auto", "tick", "sti", "isr", "timer", "release"):
            return None, "source must be auto|tick|sti|isr|timer|release"
        return {
            "times": list(times or []),
            "expected": expected,
            "source": src,
            "task": str(a.get("task") or "").strip(),
            "durations": list(durs or []),
        }, ""
    if name == AI_TOOL_SUMMARIZE_INVESTIGATION_CONTEXT:
        tools = a.get("tools_run")
        if tools is not None and not isinstance(tools, (list, tuple)):
            return None, "tools_run must be an array"
        return {
            "conclusion": str(a.get("conclusion") or "").strip(),
            "tools_run": [str(t) for t in (tools or [])],
        }, ""
    return None, f"unknown tool {name!r}"


def summarise_tool_call(name: str, args: Optional[Dict[str, Any]]) -> str:
    """One-line label for a tool card (e.g. Set cursors at 3099000, 3133000)."""
    a = dict(args or {})
    if name == AI_TOOL_SET_CURSORS:
        times = _as_float_list(a.get("timestamps"))
        if not times:
            return "Set cursors"
        shown = ", ".join(_fmt_trace_num(t) for t in times[:_MAX_CURSORS_TOOL])
        return f"Set cursors at [{shown}]"
    if name == AI_TOOL_ZOOM_TO_RANGE:
        try:
            lo, hi = float(a["start_time"]), float(a["end_time"])
            return f"Zoom to range {_fmt_trace_num(lo)}–{_fmt_trace_num(hi)}"
        except (KeyError, TypeError, ValueError):
            return "Zoom to range"
    if name == AI_TOOL_HIGHLIGHT_TASK:
        key = str(a.get("task_name_or_id") or "").strip()
        return "Clear task highlight" if not key else f"Highlight task {key}"
    if name == AI_TOOL_SET_VIEW_MODE:
        mode = str(a.get("mode") or "?").strip()
        ori = str(a.get("orientation") or "").strip()
        label = f"Set view mode {mode}"
        if ori:
            label += f", {ori}"
        return label
    if name == AI_TOOL_OPEN_CORRIDOR:
        src = str(a.get("core_from") or "").strip()
        dst = str(a.get("core_to") or "").strip()
        if src and dst:
            return f"Open corridor inspector {src} → {dst}"
        return "Open corridor inspector"
    if name == AI_TOOL_ADD_ANNOTATION:
        note = str(a.get("note") or "").strip() or "annotation"
        try:
            t = float(a.get("time"))
            return f"Add annotation at {_fmt_trace_num(t)}: {note}"
        except (TypeError, ValueError):
            return f"Add annotation: {note}"
    if name == AI_TOOL_QUERY_RAW_METRIC:
        task = str(a.get("task") or "").strip() or "?"
        metric = normalize_raw_metric(a.get("metric")) or str(a.get("metric") or "?")
        return f"Query {metric} for {task}"
    if name == AI_TOOL_EXPORT_REPORT:
        fmt = str(a.get("format") or "html").strip().lower() or "html"
        return f"Export {fmt} report"
    if name == AI_TOOL_CLEAR_MARKS:
        what = str(a.get("what") or "all").strip() or "all"
        return f"Clear marks ({what})"
    if name == AI_TOOL_RESET_VIEW:
        return "Reset view"
    if name == AI_TOOL_SEARCH_TIMELINE:
        q = str(a.get("query") or "").strip()
        mode = str(a.get("mode") or "contains").strip() or "contains"
        shown = q if len(q) <= 40 else q[:37] + "…"
        return f"Search timeline [{mode}] {shown!r}"
    if name == AI_TOOL_TRIGGER_COMPARE:
        a_tab = str(a.get("tab_a") or "0").strip() or "0"
        b_tab = str(a.get("tab_b") or "1").strip() or "1"
        return f"Compare tabs {a_tab} vs {b_tab}"
    if name == AI_TOOL_INVESTIGATE:
        fid = str(a.get("finding_id") or "").strip() or "top finding"
        depth = a.get("depth", 2)
        return f"Investigate {fid} (depth {depth})"
    if name == AI_TOOL_DETECT_ANOMALIES:
        return f"Detect anomalies (limit {a.get('limit', 10)})"
    if name == AI_TOOL_CORRELATE_EVENTS:
        return f"Correlate events for {str(a.get('task') or '?').strip() or '?'}"
    if name == AI_TOOL_FIND_CRITICAL_PATH:
        task = str(a.get("task") or "?").strip() or "?"
        ts = a.get("timestamp")
        if ts is not None:
            return f"Find critical path for {task} @ {_fmt_trace_num(ts)}"
        return f"Find critical path for {task}"
    if name == AI_TOOL_COMPARE_PERFORMANCE:
        return "Compare performance (A vs B)"
    if name == AI_TOOL_GENERATE_REPORT:
        return f"Generate {str(a.get('report_type') or 'performance')} report"
    if name == AI_TOOL_CHECK_BUDGET:
        n = len(a.get("tasks") or []) if isinstance(a.get("tasks"), (list, tuple)) else 0
        return f"Check budget ({n} task row(s))" if n else "Check budget"
    if name == AI_TOOL_OPTIMIZE:
        return f"Optimize (limit {a.get('limit', 5)})"
    if name == AI_TOOL_REGRESSION_EXPLAIN:
        return "Explain regression (A vs B)"
    if name == AI_TOOL_BOOKMARK_FINDING:
        kind = str(a.get("kind") or "evidence").strip() or "evidence"
        try:
            t = float(a.get("time"))
            return f"Bookmark {kind} at {_fmt_trace_num(t)}"
        except (TypeError, ValueError):
            return f"Bookmark {kind}"
    if name == AI_TOOL_INVESTIGATION_REPLAY:
        fid = str(a.get("finding_id") or "").strip() or "top finding"
        return f"Investigation replay ({fid})"
    if name == AI_TOOL_WHAT_IF:
        change = str(a.get("change") or "").strip()
        shown = change if len(change) <= 40 else change[:37] + "…"
        return f"What-if: {shown}" if shown else "What-if"
    if name == AI_TOOL_OPTIMIZE_EXPERIMENT:
        task = str(a.get("task") or "").strip()
        lim = a.get("limit", 5)
        return f"Optimize experiment ({task or 'auto'}, limit {lim})"
    if name == AI_TOOL_ANALYZE_TRACES:
        return "Analyze loaded traces"
    if name == AI_TOOL_BASELINE_SCORE:
        task = str(a.get("task") or "").strip()
        return f"Baseline score ({task or 'all tasks'})"
    if name == AI_TOOL_RECOMMEND_EXPERIMENTS:
        fid = str(a.get("finding_id") or "").strip()
        task = str(a.get("task") or "").strip()
        label = fid or task or "top finding"
        return f"Recommend experiments ({label})"
    if name == AI_TOOL_EXPORT_INVESTIGATION:
        return "Export investigation (JSON)"
    if name == AI_TOOL_DETECT_PRIORITY_INVERSION:
        task = str(a.get("task") or "").strip()
        return f"Detect priority inversion ({task or 'all tasks'})"
    if name == AI_TOOL_FIND_RELATED_FINDINGS:
        fid = str(a.get("finding_id") or "").strip()
        task = str(a.get("task") or "").strip()
        metric = str(a.get("metric") or "").strip()
        label = fid or task or metric or "top finding"
        return f"Find related findings ({label})"
    if name == AI_TOOL_COMPARE_TASKS:
        a_task = str(a.get("task_a") or "?").strip() or "?"
        b_task = str(a.get("task_b") or "?").strip() or "?"
        return f"Compare tasks {a_task} vs {b_task}"
    if name == AI_TOOL_EXPLAIN_FINDING:
        fid = str(a.get("finding_id") or "").strip() or "top finding"
        level = str(a.get("level") or "technical").strip() or "technical"
        return f"Explain finding {fid} ({level})"
    if name == AI_TOOL_INTERPRET_QUERY:
        q = str(a.get("question") or "").strip()
        shown = q if len(q) <= 40 else q[:37] + "…"
        return f"Interpret query {shown!r}" if shown else "Interpret query"
    if name == AI_TOOL_VALIDATE_EXPERIMENT:
        return "Validate experiment (expected vs actual)"
    if name == AI_TOOL_MANAGE_HYPOTHESES:
        hid = str(a.get("hypothesis_id") or "").strip() or "hypothesis"
        st = str(a.get("status") or "").strip() or "status"
        return f"Hypothesis {hid} → {st}"
    if name == AI_TOOL_PLAN_INVESTIGATION:
        return "Plan investigation"
    if name == AI_TOOL_SUGGEST_SCOPE:
        return "Suggest investigation scope"
    if name == AI_TOOL_DETECT_CONTRADICTIONS:
        return "Detect contradictions"
    if name == AI_TOOL_ASSESS_EVIDENCE_SUFFICIENCY:
        return "Assess evidence sufficiency"
    if name == AI_TOOL_CLUSTER_FINDINGS:
        return "Cluster findings"
    if name == AI_TOOL_GENERATE_FINGERPRINT:
        return "Generate trace fingerprint"
    if name == AI_TOOL_FIND_SIMILAR_INVESTIGATIONS:
        return "Find similar investigations"
    if name == AI_TOOL_REGRESSION_LOCALIZE:
        return "Localize regression"
    if name == AI_TOOL_BUILD_CAUSAL_CHAIN:
        return "Build causal chain"
    if name == AI_TOOL_GENERATE_EXPERIMENT_PLAN:
        return "Generate experiment plan"
    if name == AI_TOOL_RECORD_EXPERIMENT_OUTCOME:
        return "Record experiment outcome"
    if name == AI_TOOL_SCORE_INVESTIGATION:
        return "Score investigation"
    if name == AI_TOOL_ANALYZE_TEMPORAL_CAUSALITY:
        return "Analyze temporal causality"
    if name == AI_TOOL_BUILD_TASK_DEPENDENCY_GRAPH:
        return "Build task dependency graph"
    if name == AI_TOOL_DECOMPOSE_RESPONSE_TIME:
        return "Decompose response time"
    if name == AI_TOOL_RANK_ROOT_CAUSES:
        return "Rank root causes"
    if name == AI_TOOL_VERIFY_CLAIM:
        return "Verify claim"
    if name == AI_TOOL_CHALLENGE_CONCLUSION:
        return "Challenge conclusion"
    if name == AI_TOOL_INVESTIGATION_MEMORY:
        return "Investigation memory"
    if name == AI_TOOL_CLUSTER_INCIDENTS:
        return "Cluster incidents"
    if name == AI_TOOL_CLOSE_INVESTIGATION:
        return "Close investigation"
    if name == AI_TOOL_ANALYZE_DISTRIBUTION:
        return "Analyze distribution"
    if name == AI_TOOL_ANALYZE_PERIODICITY:
        return "Analyze periodicity"
    if name == AI_TOOL_SUMMARIZE_INVESTIGATION_CONTEXT:
        return "Summarize investigation context"
    return name.replace("_", " ")


def tool_result_payload(ok: bool, message: str, **extra: Any) -> Dict[str, Any]:
    data = {"ok": bool(ok), "message": str(message)}
    data.update(extra)
    return data


def format_tool_result_content(result: Dict[str, Any]) -> str:
    """JSON string sent back to the model as ``role: tool`` content."""
    return json.dumps(result, default=str)


def canonical_assistant_tool_message(
    content: Any,
    tool_calls: Sequence[Dict[str, Any]],
) -> Dict[str, Any]:
    """OpenAI-shaped assistant turn with ``tool_calls`` (Gemini-safe)."""
    calls_out: List[Dict[str, Any]] = []
    for i, call in enumerate(tool_calls or []):
        if not isinstance(call, dict):
            continue
        name = str(call.get("name") or "").strip()
        if not name:
            continue
        cid = _tool_call_id(call, i)
        args = call.get("arguments")
        if isinstance(args, str):
            arg_s = args
        else:
            arg_s = json.dumps(
                args if isinstance(args, dict) else {}, default=str)
        entry: Dict[str, Any] = {
            "id": cid,
            "type": "function",
            "function": {"name": name, "arguments": arg_s},
        }
        sig = str(call.get("thought_signature") or "").strip() or (
            thought_signature_from_obj(call)
        )
        if sig:
            attach_thought_signature(entry, sig)
        calls_out.append(entry)
    text = message_content_text(content) if content is not None else ""
    msg: Dict[str, Any] = {"role": "assistant", "content": text or None}
    if calls_out:
        msg["tool_calls"] = calls_out
    return msg


def tool_result_message(
    *,
    tool_call_id: str,
    name: str,
    content: Any,
) -> Dict[str, Any]:
    """``role=tool`` follow-up. Gemini requires a non-empty function name."""
    cid = str(tool_call_id or "").strip() or "call_0"
    fname = str(name or "").strip()
    if isinstance(content, str):
        body = content
    elif isinstance(content, dict):
        body = format_tool_result_content(content)
    else:
        body = format_tool_result_content(
            {"ok": False, "message": str(content or "")})
    out: Dict[str, Any] = {
        "role": "tool",
        "tool_call_id": cid,
        "content": body,
    }
    if fname:
        out["name"] = fname
    return out


def normalize_tool_chat_messages(
    messages: Sequence[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """Fill ``name`` on tool follow-ups (Gemini OpenAI-compat).

    Gemini maps ``role=tool`` to ``function_response`` and rejects an empty
    name. Match by ``tool_call_id``, then by order after the last assistant
    tool_calls.
    """
    out: List[Dict[str, Any]] = []
    unused: List[Tuple[str, str]] = []
    for msg in messages or []:
        if not isinstance(msg, dict):
            continue
        role = str(msg.get("role") or "")
        if role == "assistant":
            extracted = extract_tool_calls(msg)
            if extracted:
                canon = canonical_assistant_tool_message(
                    msg.get("content"), extracted)
                out.append(canon)
                unused = [
                    (str(c.get("id") or ""), str(c.get("name") or "").strip())
                    for c in extract_tool_calls(canon)
                    if str(c.get("id") or "") and str(c.get("name") or "").strip()
                ]
            else:
                out.append(dict(msg))
                unused = []
            continue
        if role == "tool":
            copied = dict(msg)
            cid = str(copied.get("tool_call_id") or copied.get("id") or "").strip()
            name = str(copied.get("name") or "").strip() or _tool_call_name(copied)
            if not name and cid:
                for i, (uid, uname) in enumerate(unused):
                    if uid == cid:
                        name = uname
                        unused.pop(i)
                        break
            if not name and unused:
                uid, uname = unused.pop(0)
                name = uname
                if not cid:
                    cid = uid
            elif name and cid:
                unused = [(i, n) for i, n in unused if i != cid]
            if cid:
                copied["tool_call_id"] = cid
            if name:
                copied["name"] = name
            out.append(copied)
            continue
        out.append(dict(msg))
    return out


def parse_ai_auto_apply(value: Any) -> bool:
    """Settings → AI auto-apply flag (default False = require confirm)."""
    if value is True:
        return True
    if value is False or value is None:
        return False
    return str(value).strip().lower() in ("1", "true", "yes", "on")


def parse_ai_mcp_log(value: Any) -> bool:
    """Settings → AI MCP message debug log (default False)."""
    return parse_ai_auto_apply(value)


def max_tool_rounds(template_id: str = "") -> int:
    return max_tool_rounds_for_template(template_id, _MAX_TOOL_ROUNDS)


_TASK_ID_SUFFIX_RE = re.compile(r"\[(\d+)\]\s*$")
_TASK_EMBEDDED_RE = re.compile(r"([A-Za-z_][\w]*\[\d+\])")
_CORE_SUFFIX_RE = re.compile(r"\s*\((?:core\s*)?\d+\)\s*$", re.IGNORECASE)
_CORE_NUM_RE = re.compile(r"^(?:core[\s_-]*)?(\d+)$", re.IGNORECASE)
_CORE_SHORT_RE = re.compile(r"^c(\d+)$", re.IGNORECASE)


def normalize_task_lookup_query(task_name_or_id: str) -> str:
    """Strip mermaid decorations such as ``Low[266] (Core 0)`` → ``Low[266]``."""
    text = (task_name_or_id or "").strip()
    if not text:
        return ""
    stripped = _CORE_SUFFIX_RE.sub("", text).strip() or text
    m = _TASK_EMBEDDED_RE.search(stripped)
    return m.group(1) if m else stripped


def task_lookup_keys(task_name_or_id: str) -> List[str]:
    """Candidate keys for resolving a highlight target (name, id, merge key)."""
    raw = (task_name_or_id or "").strip()
    if not raw:
        return []
    keys: List[str] = []
    for alias in _task_match_aliases(raw):
        if alias not in keys:
            keys.append(alias)
        low = alias.lower()
        if low not in keys:
            keys.append(low)
    return keys


def _task_match_aliases(raw: str) -> List[str]:
    """Display name / id / merge-key spellings that should match *raw*."""
    text = (raw or "").strip()
    if not text:
        return []
    aliases = [text]
    if text.startswith("\x00"):
        sep = text.find("\x00", 1)
        if sep > 0:
            tid, name = text[1:sep], text[sep + 1:]
            if name and name != "TICK":
                aliases.extend((f"{name}[{tid}]", name, tid))
            elif name:
                aliases.append(name)
        return [a for a in aliases if a]
    m = _TASK_ID_SUFFIX_RE.search(text)
    if m:
        # Prefer the capture; fall back to the bracket body if a bundle
        # name-collision ever clobbers this pattern (no groups).
        tid = m.group(1) if m.lastindex else m.group(0).strip("[]")
        if tid:
            aliases.append(tid)
        prefix = text[: m.start()].strip()
        if prefix:
            aliases.append(prefix)
    if text.isdigit():
        aliases.append(f"[{text}]")
    return [a for a in aliases if a]


def resolve_task_key(
    task_name_or_id: str,
    candidates: Sequence[str],
) -> Optional[str]:
    """Pick the best matching task/merge key from *candidates*."""
    raw = (task_name_or_id or "").strip()
    if not raw:
        return None
    names = [str(c) for c in candidates if c]
    if not names:
        return None
    queries = [raw]
    norm = normalize_task_lookup_query(raw)
    if norm and norm not in queries:
        queries.append(norm)

    exact = {n: n for n in names}
    lower = {n.lower(): n for n in names}
    by_alias: Dict[str, List[str]] = {}
    for name in names:
        for alias in _task_match_aliases(name):
            bucket = by_alias.setdefault(alias.lower(), [])
            if name not in bucket:
                bucket.append(name)

    for want in queries:
        if want in exact:
            return exact[want]
        if want.lower() in lower:
            return lower[want.lower()]
        hits = by_alias.get(want.lower()) or []
        if len(hits) == 1:
            return hits[0]
        if hits and want.isdigit():
            return hits[0]
        want_l = want.lower()
        prefix: List[str] = []
        contains: List[str] = []
        for alias, origs in by_alias.items():
            if alias.startswith(want_l):
                prefix.extend(origs)
            if want_l in alias:
                contains.extend(origs)
        prefix_u = list(dict.fromkeys(prefix))
        if len(prefix_u) == 1:
            return prefix_u[0]
        contains_u = list(dict.fromkeys(contains))
        if len(contains_u) == 1:
            return contains_u[0]
    return None


def _core_match_aliases(raw: str) -> List[str]:
    """Core_0 / Core 0 / 0 / c0 spellings that should match *raw*."""
    text = (raw or "").strip()
    if not text:
        return []
    aliases = [text]
    compact = re.sub(r"[\s_-]+", "_", text)
    if compact not in aliases:
        aliases.append(compact)
    spaced = text.replace("_", " ")
    if spaced not in aliases:
        aliases.append(spaced)
    m = _CORE_NUM_RE.match(text) or _CORE_SHORT_RE.match(text)
    if m:
        n = str(int(m.group(1)))
        aliases.extend((n, f"Core_{n}", f"core_{n}", f"Core {n}", f"c{n}", f"C{n}"))
    return [a for a in dict.fromkeys(aliases) if a]


def resolve_core_key(
    core_name_or_id: str,
    candidates: Sequence[str],
) -> Optional[str]:
    """Pick the best matching core name from *candidates* (e.g. Core_0)."""
    want = (core_name_or_id or "").strip()
    if not want:
        return None
    names = [str(c) for c in candidates if c]
    if not names:
        return None
    if want in names:
        return want
    lower = {n.lower(): n for n in names}
    if want.lower() in lower:
        return lower[want.lower()]
    by_alias: Dict[str, List[str]] = {}
    for name in names:
        for alias in _core_match_aliases(name):
            bucket = by_alias.setdefault(alias.lower(), [])
            if name not in bucket:
                bucket.append(name)
    hits: List[str] = []
    for alias in _core_match_aliases(want):
        for orig in by_alias.get(alias.lower(), []):
            if orig not in hits:
                hits.append(orig)
    if hits:
        return hits[0]
    return None


def _csv_escape_rows(rows: Sequence[Sequence[Any]]) -> str:
    buf = io.StringIO()
    writer = csv.writer(buf, lineterminator="\n")
    for row in rows:
        writer.writerow(["" if c is None else str(c) for c in row])
    return buf.getvalue()


def build_ai_report_csv(
    *,
    meta: Optional[Dict[str, Any]] = None,
    gui: Optional[Dict[str, Any]] = None,
    findings: str = "",
    annotations: Optional[Sequence[Dict[str, Any]]] = None,
    conversation: str = "",
) -> str:
    """Tabular AI report (findings + GUI state + conversation)."""
    rows: List[List[str]] = [["section", "key", "value"]]
    for key, val in dict(meta or {}).items():
        rows.append(["meta", str(key), str(val)])
    gui_d = dict(gui or {})
    cursors = gui_d.pop("cursors", None)
    if cursors is not None:
        if isinstance(cursors, (list, tuple)):
            rows.append(["gui", "cursors", ";".join(f"{c:g}" if isinstance(c, (int, float)) else str(c) for c in cursors)])
        else:
            rows.append(["gui", "cursors", str(cursors)])
    for key, val in gui_d.items():
        if key == "annotations":
            continue
        rows.append(["gui", str(key), str(val)])
    ann_list = list(annotations or [])
    if not ann_list and isinstance(gui, dict):
        extra = gui.get("annotations")
        if isinstance(extra, (list, tuple)):
            ann_list = list(extra)
    for ann in ann_list:
        if not isinstance(ann, dict):
            continue
        rows.append(["annotation", str(ann.get("time", "")), str(ann.get("note", ""))])
    for i, line in enumerate((findings or "").splitlines()):
        if line.strip():
            rows.append(["finding", str(i + 1), line])
    for i, line in enumerate((conversation or "").splitlines()):
        rows.append(["conversation", str(i + 1), line])
    return _csv_escape_rows(rows)


def _html_escape(text: Any) -> str:
    return (
        str(text or "")
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )



_TASK_FINDING_RE = re.compile(r"\b([A-Za-z][A-Za-z0-9_.-]*\[\d+\])")
_CORE_FINDING_RE = re.compile(r"\b(?:Core[_\s-]?(\d+)|C(\d+))\b", re.IGNORECASE)
_DUR_FINDING_RE = re.compile(r"\bdur(?:ation)?\s*=\s*([0-9]+(?:\.[0-9]+)?)", re.IGNORECASE)
_SEVERITY_RE = re.compile(
    r"\[?\s*(CRITICAL|WARNING|WARN|ERROR|INFO|HIGH|MEDIUM|LOW)\s*\]?",
    re.IGNORECASE,
)


def _fmt_evidence_delta(delta: float) -> str:
    if delta < 1:
        return f"{delta * 1_000_000:.0f} µs"
    if delta < 1000:
        return f"{delta:.6g} s"
    return f"{delta:.0f}"


def filter_entries_for_ai_report(entries: Optional[Sequence[Any]] = None) -> List[Any]:
    """Drop tool-usage cards from saved HTML/Markdown/Text (prose + Evidence only).

    Keeps user / assistant / evidence turns. Omits tools-only assistant shells
    (for example a Calculation card with no written reply) and strips ``tools``
    from every remaining entry so export never shows Evidence queries / Apply.
    """
    out: List[Any] = []
    for entry in entries or []:
        tools: List[Any] = []
        if isinstance(entry, dict):
            tools = list(entry.get("tools") or [])
        text = ""
        role = ""
        if isinstance(entry, dict):
            text = str(entry.get("text") or entry.get("content") or "")
            role = str(entry.get("role") or "")
        elif isinstance(entry, (list, tuple)) and len(entry) >= 2:
            role = str(entry[0] or "")
            text = str(entry[1] or "")
        # Tools-only assistant bubble (no prose) — omit entirely.
        if tools and not text.strip() and role != "evidence":
            continue
        low = text.lower()
        if (
            ("export html report" in low or "export_report" in low)
            and "pending" in low
            and len(text.strip()) < 80
        ):
            continue
        if isinstance(entry, dict) and "tools" in entry:
            entry = dict(entry)
            entry.pop("tools", None)
        out.append(entry)
    return out


def _cursor_bounds_from_gui(gui: Optional[dict] = None) -> Tuple[Optional[float], Optional[float]]:
    data = gui if isinstance(gui, dict) else {}
    cursors = data.get("cursors")
    if not isinstance(cursors, (list, tuple)) or len(cursors) < 2:
        return None, None
    try:
        vals = [float(c) for c in cursors]
    except (TypeError, ValueError):
        return None, None
    return min(vals), max(vals)


def _fmt_report_time(t: Any) -> str:
    try:
        v = float(t)
    except (TypeError, ValueError):
        return str(t or "")
    if abs(v) >= 1000:
        return f"{v:.0f}"
    return f"{v:.6g}"


def _evidence_in_scope(ev: dict, lo: Optional[float], hi: Optional[float]) -> bool:
    if lo is None or hi is None:
        return True
    start, stop, t = ev.get("start"), ev.get("stop"), ev.get("time")
    if start is not None and stop is not None:
        return _overlaps_range(start, stop, lo, hi)
    if t is not None:
        return _in_time_range(t, lo, hi)
    return True


def _partition_report_evidence(
    evidence: Sequence[Any],
    lo: Optional[float],
    hi: Optional[float],
) -> Tuple[List[dict], List[dict]]:
    kept: List[dict] = []
    rejected: List[dict] = []
    for ev in evidence or []:
        if not isinstance(ev, dict):
            continue
        if _evidence_in_scope(ev, lo, hi):
            kept.append(ev)
        else:
            rejected.append(ev)
    return kept, rejected


def _status_label_for_report(key: str) -> str:
    return {
        "confirmed": "Confirmed",
        "correlated": "Correlated",
        "suspected": "Suspected",
        "not_observed": "Not observed",
        "insufficient": "Insufficient data",
    }.get(str(key or ""), "Suspected")


def _ranked_findings_from_text(findings: str) -> List[Dict[str, str]]:
    rows: List[Dict[str, str]] = []
    for line in str(findings or "").splitlines():
        raw = line.strip()
        if not raw:
            continue
        sev = "Info"
        m = _SEVERITY_RE.search(raw)
        if m:
            token = m.group(1).upper()
            sev = {
                "CRITICAL": "High", "ERROR": "High", "HIGH": "High",
                "WARNING": "Medium", "WARN": "Medium", "MEDIUM": "Medium",
                "INFO": "Info", "LOW": "Info",
            }.get(token, "Info")
        task_m = _TASK_FINDING_RE.search(raw)
        task = task_m.group(1) if task_m else "—"
        title = _SEVERITY_RE.sub("", raw)
        title = re.sub(r"^\d+[\.)]\s*", "", title).strip(" -–—:")
        rows.append({
            "severity": sev,
            "finding": title[:160] or raw[:160],
            "task": task,
            "scope": "Current scope",
            "confidence": "Suspected",
        })
        if len(rows) >= 12:
            break
    return rows


def _html_table(headers: Sequence[str], rows: Sequence[Sequence[Any]]) -> str:
    head = "".join(f"<th>{_html_escape(h)}</th>" for h in headers)
    body = []
    for row in rows:
        cells = "".join(f"<td>{_html_escape(c)}</td>" for c in row)
        body.append(f"<tr>{cells}</tr>")
    return (
        f'<table class="ai-md-table"><thead><tr>{head}</tr></thead>'
        f"<tbody>{''.join(body)}</tbody></table>"
    )


def _details_block(title: str, inner_html: str, *, open_: bool = False) -> str:
    op = " open" if open_ else ""
    return (
        f"<details class=\"report-appendix\"{op}>"
        f"<summary>{_html_escape(title)}</summary>"
        f"<div class=\"appendix-body\">{inner_html}</div>"
        f"</details>"
    )



def build_ai_report_html(
    *,
    meta: Optional[Dict[str, Any]] = None,
    gui: Optional[Dict[str, Any]] = None,
    findings: str = "",
    annotations: Optional[Sequence[Dict[str, Any]]] = None,
    conversation_html: str = "",
    evidence_payload: Optional[Dict[str, Any]] = None,
    analysis_complete: bool = True,
    report_mode: str = "summary",
) -> str:
    """Standalone HTML diagnostic report (summary first; transcript in appendix)."""
    import datetime

    stamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    mode = str(report_mode or "summary").strip().lower()
    if mode not in ("summary", "technical", "full"):
        mode = "summary"
    meta_d = dict(meta or {})
    gui_d = dict(gui or {})
    payload = evidence_payload if isinstance(evidence_payload, dict) else {}
    lo, hi = _cursor_bounds_from_gui(gui_d)

    status_key = conclusion_status_from_payload(payload) if payload else (
        "insufficient" if not str(findings or "").strip() else "suspected"
    )
    status_label = _status_label_for_report(status_key)
    completeness = "Complete" if analysis_complete else "Analysis incomplete"
    overall = "Warning" if status_key in ("suspected", "insufficient") else (
        "OK" if status_key in ("confirmed", "correlated", "not_observed") else "Warning"
    )

    # --- Header / executive summary ---
    conclusion = str(payload.get("conclusion") or "").strip()
    subtitle_bits = [
        f"Scope: {_html_escape(meta_d.get('scope') or 'full trace')}",
        f"Span: {_html_escape(meta_d.get('span') or '—')}",
        f"Cores: {_html_escape(meta_d.get('cores') or '—')}",
        f"Analysis: {_html_escape(completeness)}",
    ]
    if lo is not None and hi is not None:
        subtitle_bits.insert(
            0,
            f"Cursor: {_html_escape(_fmt_report_time(lo))}–{_html_escape(_fmt_report_time(hi))}",
        )
    exec_lines = [
        f'<p class="status-row"><span class="badge">{_html_escape(overall)}</span> '
        f'<span class="badge badge-status">{_html_escape(status_label)}</span> '
        f'<span class="badge badge-{"ok" if analysis_complete else "warn"}">'
        f"{_html_escape(completeness)}</span></p>",
        f'<p class="report-scope">{" · ".join(subtitle_bits)}</p>',
    ]
    if not analysis_complete:
        exec_lines.append(
            '<p class="warn-banner"><strong>Analysis incomplete.</strong> '
            "Export again after the investigation finishes for a consistent snapshot."
            "</p>"
        )
    if conclusion:
        exec_lines.append(f"<p>{_html_escape(conclusion)}</p>")
    elif str(findings or "").strip():
        first = next(
            (ln.strip() for ln in str(findings).splitlines() if ln.strip()),
            "",
        )
        if first:
            exec_lines.append(f"<p>{_html_escape(first[:320])}</p>")
    else:
        exec_lines.append("<p>No consolidated finding yet.</p>")

    # --- Coverage ---
    cov_rows: List[List[str]] = []
    checks = [c for c in (payload.get("checks") or []) if isinstance(c, dict)]
    quality = payload.get("evidence_quality") if isinstance(
        payload.get("evidence_quality"), dict) else {}
    qflags = quality.get("flags") if isinstance(quality.get("flags"), dict) else {}
    if checks:
        for c in checks[:12]:
            cov_rows.append([
                str(c.get("label") or c.get("metric") or "check"),
                str(c.get("status") or "Not evaluated"),
                str(c.get("detail") or "—")[:120],
            ])
    elif qflags:
        for key, title in (
            ("direct_evidence", "Direct evidence"),
            ("timeline_correlation", "Timeline correlation"),
            ("metric_correlation", "Metric correlation"),
        ):
            val = qflags.get(key)
            if val is True:
                cell = "Observed"
            elif val is False:
                cell = "Not observed"
            elif val is None:
                cell = "Not evaluated"
            else:
                cell = str(val)
            cov_rows.append([title, cell, "—"])
    coverage_html = (
        _html_table(["Category", "Result", "Strongest evidence"], cov_rows)
        if cov_rows else "<p>No coverage checklist recorded for this session.</p>"
    )

    # --- Ranked findings ---
    ranked = _ranked_findings_from_text(findings)
    if not ranked and conclusion:
        ranked = [{
            "severity": "Medium",
            "finding": conclusion[:160],
            "task": "—",
            "scope": "Current scope",
            "confidence": status_label,
        }]
    ranked_html = (
        _html_table(
            ["Severity", "Finding", "Task", "Scope", "Confidence"],
            [[r["severity"], r["finding"], r["task"], r["scope"], r["confidence"]]
             for r in ranked],
        ) if ranked else "<p>No ranked findings.</p>"
    )

    # --- Evidence table (in-scope) + rejected ---
    evidence = [e for e in (payload.get("evidence") or []) if isinstance(e, dict)]
    kept, rejected = _partition_report_evidence(evidence, lo, hi)
    ev_rows = []
    for ev in kept[:40]:
        label = str(ev.get("label") or "event")
        task_m = _TASK_FINDING_RE.search(label)
        task = str(ev.get("task") or (task_m.group(1) if task_m else "—"))
        core = str(ev.get("core") or "").strip()
        if not core:
            core_m = _CORE_FINDING_RE.search(label)
            core = f"Core {core_m.group(1) or core_m.group(2)}" if core_m else "—"
        t = ev.get("time", ev.get("start", ""))
        dur = ""
        if ev.get("start") is not None and ev.get("stop") is not None:
            try:
                delta = float(ev["stop"]) - float(ev["start"])
                if delta > 0:
                    dur = _fmt_evidence_delta(delta)
            except (TypeError, ValueError):
                dur = ""
        if not dur:
            try:
                delta = float(ev.get("duration", ev.get("gap")))
                if delta > 0:
                    dur = _fmt_evidence_delta(delta)
            except (TypeError, ValueError):
                dur = ""
        if not dur:
            dur_m = _DUR_FINDING_RE.search(label)
            if dur_m:
                try:
                    delta = float(dur_m.group(1))
                    if delta > 0:
                        dur = _fmt_evidence_delta(delta)
                except (TypeError, ValueError):
                    pass
        ev_rows.append([
            _fmt_report_time(t), label, task,
            core or "—", dur or "—", "In scope",
        ])
    evidence_html = (
        _html_table(
            ["Time", "Event", "Task", "Core", "Duration", "Scope"],
            ev_rows,
        ) if ev_rows else "<p>No in-scope evidence rows.</p>"
    )
    rejected_rows = []
    for ev in rejected[:40]:
        rejected_rows.append([
            _fmt_report_time(ev.get("time", ev.get("start", ""))),
            str(ev.get("label") or "event"),
            "Excluded",
        ])
    rejected_html = (
        _html_table(["Time", "Event", "Scope"], rejected_rows)
        if rejected_rows else "<p>None.</p>"
    )

    # --- Next action ---
    falsify = payload.get("falsify") if isinstance(payload.get("falsify"), dict) else {}
    nxt = str(falsify.get("next_check") or "").strip()
    next_html = f"<p>{_html_escape(nxt)}</p>" if nxt else "<p>No next action recorded.</p>"

    # --- Finding detail (observation vs interpretation) ---
    chain = str(payload.get("evidence_chain") or "").strip()
    detail_html = ""
    if conclusion or chain:
        detail_html = (
            f"<p><strong>Observation</strong> — {_html_escape(conclusion or 'See evidence table.')}</p>"
            f"<p><strong>Interpretation</strong> — "
            f"{_html_escape(chain or 'Cause not confirmed from direct events alone.')}</p>"
            f"<p><strong>Confidence</strong> — {_html_escape(status_label)} "
            f"(derived from evidence status; not a free-form model claim).</p>"
        )

    # --- Appendix pieces ---
    meta_rows = "".join(
        f"<tr><th>{_html_escape(k)}</th><td>{_html_escape(v)}</td></tr>"
        for k, v in meta_d.items()
    )
    gui_rows = []
    for key, val in gui_d.items():
        if key == "annotations":
            continue
        if key == "cursors" and isinstance(val, (list, tuple)):
            # Preserve precision (avoid scientific notation for integers).
            bits = []
            for c in val:
                try:
                    bits.append(_fmt_report_time(float(c)))
                except (TypeError, ValueError):
                    bits.append(str(c))
            val = ", ".join(bits)
        gui_rows.append(
            f"<tr><th>{_html_escape(key)}</th><td>{_html_escape(val)}</td></tr>"
        )
    anns = list(annotations or [])
    if not anns and isinstance(gui_d.get("annotations"), list):
        anns = list(gui_d["annotations"])
    ann_rows = "".join(
        f"<tr><td>{_html_escape(a.get('time', ''))}</td>"
        f"<td>{_html_escape(a.get('note', ''))}</td></tr>"
        for a in anns if isinstance(a, dict)
    ) or "<tr><td colspan=\"2\">None</td></tr>"
    findings_body = (
        f"<pre>{_html_escape(findings)}</pre>" if (findings or "").strip()
        else "<p>No findings for the current scope.</p>"
    )
    conv = (conversation_html or "").strip() or "<p>No conversation.</p>"

    appendix_open = mode == "full"
    appendix = (
        _details_block("Rejected evidence (out of cursor window)", rejected_html)
        + _details_block("Raw Analysis Findings", findings_body)
        + _details_block(
            "GUI state",
            f'<table class="gui-table">{"".join(gui_rows) or "<tr><td>None</td></tr>"}</table>',
        )
        + _details_block(
            "Annotations",
            f'<table class="ann-table"><tr><th>Time</th><th>Note</th></tr>{ann_rows}</table>',
        )
        + _details_block(
            "Report metadata",
            f'<table class="meta-table">{meta_rows or "<tr><td>None</td></tr>"}</table>',
        )
        + _details_block(
            "Conversation export",
            conv,
            open_=appendix_open,
        )
    )
    if mode == "technical":
        # Technical mode opens coverage-adjacent appendix pieces.
        pass

    note = (
        '<p class="export-note">Standalone export: <code>btfjump:</code> / '
        "<code>jump:</code> links require BTFViewer. Timestamps above are "
        "readable forms of the raw cursor values.</p>"
    )

    body = (
        "<!--TOC-->\n"
        f'<section class="report-card">\n'
        f"<h2>Executive summary</h2>\n"
        f"{''.join(exec_lines)}\n"
        f"</section>\n"
        f'<section class="report-card">\n'
        f"<h2>Coverage summary</h2>\n"
        f"{coverage_html}\n"
        f"</section>\n"
        f'<section class="report-card">\n'
        f"<h2>Ranked findings</h2>\n"
        f"{ranked_html}\n"
        f"</section>\n"
        f'<section class="report-card">\n'
        f"<h2>Finding details</h2>\n"
        f"{detail_html or '<p>See ranked findings and evidence table.</p>'}\n"
        f"</section>\n"
        f'<section class="report-card">\n'
        f"<h2>Evidence</h2>\n"
        f"{evidence_html}\n"
        f"</section>\n"
        f'<section class="report-card">\n'
        f"<h2>Next action</h2>\n"
        f"{next_html}\n"
        f"</section>\n"
        f'<section class="report-card">\n'
        f"<h2>Appendix</h2>\n"
        f"{appendix}\n"
        f"{note}\n"
        f"</section>\n"
        f"{HTML_REPORT_TOC_SCRIPT}\n"
    )
    report = btf_html_report_document(
        "AI Diagnostic Report",
        body,
        subtitle=f"Saved {stamp} · mode={mode}",
        extra_css=HTML_REPORT_TOC_CSS,
        doc_title="BTFViewer — AI Report",
    )
    # Same Expand all / Collapse all TOC chrome as Statistics HTML reports.
    return html_apply_collapsible_toc(
        report,
        default_expanded=("Executive summary",),
    )


def _in_time_range(t: Any, lo: Optional[float], hi: Optional[float]) -> bool:
    if lo is None or hi is None:
        return True
    try:
        v = float(t)
    except (TypeError, ValueError):
        return False
    return lo <= v <= hi


def _overlaps_range(start: Any, stop: Any, lo: Optional[float], hi: Optional[float]) -> bool:
    if lo is None or hi is None:
        return True
    try:
        a, b = float(start), float(stop)
    except (TypeError, ValueError):
        return False
    return b > lo and a < hi


def search_timeline_hits(
    trace: Any,
    query: str,
    mode: str = "contains",
    annotations: Optional[Sequence[Any]] = None,
) -> Dict[str, Any]:
    """Find-panel search for the AI ``search_timeline`` tool."""
    # Prefer FIND_RECOMPUTE: the monolith may also define methods named
    # recompute_find_hits; FIND_RECOMPUTE is the free-function alias.
    recompute = globals().get("FIND_RECOMPUTE") or globals().get("recompute_find_hits")
    if recompute is None:
        try:
            from .mvvm.find_logic import recompute_find_hits as recompute
        except ImportError:
            pass

    q = str(query or "").strip()
    if not q:
        return tool_result_payload(False, "query must be a non-empty string")
    if trace is None:
        return tool_result_payload(False, "No trace loaded")
    if recompute is None:
        return tool_result_payload(False, "Find engine unavailable")
    find_mode = "sti" if str(mode or "").lower() in ("tags", "tag", "sti") else str(mode or "contains")
    anns: List[Any] = []
    for a in annotations or []:
        anns.append(a)
    try:
        hits, status = recompute(trace, q, find_mode, anns)
    except Exception as exc:
        return tool_result_payload(False, f"Find engine error: {exc}")
    status_s = str(status or "")
    if status_s in ("Regex error", "Regex too long"):
        return tool_result_payload(False, status_s)
    shown = list(hits[:_MAX_SEARCH_HITS])
    return tool_result_payload(
        True,
        f"{len(hits)} match(es) for {q!r} ({find_mode})",
        data={
            "times": shown,
            "count": len(hits),
            "mode": find_mode,
            "truncated": len(hits) > _MAX_SEARCH_HITS,
        },
    )


def _task_candidates_from_trace(trace: Any) -> List[str]:
    names: List[str] = []
    for t in list(getattr(trace, "tasks", None) or []):
        names.append(str(t))
    smap = getattr(trace, "seg_map_by_merge_key", None)
    if isinstance(smap, dict):
        names.extend(str(k) for k in smap.keys())
    web_map = getattr(trace, "segByMergeKey", None)
    if web_map is not None and hasattr(web_map, "keys"):
        try:
            names.extend(str(k) for k in web_map.keys())
        except Exception:
            pass
    repr_map = getattr(trace, "task_repr", None) or getattr(trace, "taskRepr", None)
    if isinstance(repr_map, dict):
        names.extend(str(v) for v in repr_map.values() if v)
        names.extend(str(k) for k in repr_map.keys())
    return names


def _segs_for_mk(trace: Any, mk: str) -> List[Any]:
    smap = getattr(trace, "seg_map_by_merge_key", None)
    if isinstance(smap, dict) and mk in smap:
        return list(smap.get(mk) or [])
    web_map = getattr(trace, "segByMergeKey", None)
    if web_map is None:
        return []
    getter = getattr(web_map, "get", None)
    if callable(getter):
        return list(getter(mk) or [])
    try:
        return list(web_map[mk])  # type: ignore[index]
    except Exception:
        return []


def _medium_labels(ep: Any) -> List[str]:
    out: List[str] = []
    for item in getattr(ep, "medium_tasks", None) or getattr(ep, "mediumTasks", None) or []:
        if isinstance(item, str):
            if item:
                out.append(item)
        elif isinstance(item, dict):
            label = str(item.get("label") or item.get("mk") or "")
            if label:
                out.append(label)
        else:
            label = str(getattr(item, "label", "") or "")
            if label:
                out.append(label)
    return out


def query_raw_metric(
    trace: Any,
    task: str,
    metric: str,
    *,
    lo: Optional[float] = None,
    hi: Optional[float] = None,
    findings_text: str = "",
) -> Dict[str, Any]:
    """Return a tool-result payload with per-task samples for *metric*."""
    if trace is None:
        return tool_result_payload(False, "No trace loaded")
    metric_id = normalize_raw_metric(metric)
    if not metric_id:
        return tool_result_payload(
            False, "metric must be one of: " + ", ".join(AI_RAW_METRIC_NAMES))
    resolved = resolve_task_key(str(task or "").strip(), _task_candidates_from_trace(trace))
    if not resolved:
        return tool_result_payload(False, f"Unknown task {task!r}")
    try:
        from .parser import _task_merge_key
        mk = _task_merge_key(resolved)
    except Exception:
        mk = resolved
    repr_map = getattr(trace, "task_repr", None) or getattr(trace, "taskRepr", None) or {}
    label = ""
    if isinstance(repr_map, dict):
        label = str(repr_map.get(mk) or repr_map.get(resolved) or "")
    if not label:
        label = str(resolved)
    scope = {"lo": lo, "hi": hi} if lo is not None and hi is not None else None
    data: Dict[str, Any] = {
        "task": label,
        "task_key": mk,
        "metric": metric_id,
        "scope": scope,
    }
    if metric_id == AI_RAW_METRIC_FINDINGS:
        aliases = [a for a in task_lookup_keys(task) + task_lookup_keys(label) + [label, str(resolved)] if a]
        hits = []
        for line in (findings_text or "").splitlines():
            low = line.lower()
            if any(a.lower() in low for a in aliases):
                hits.append(line)
        truncated = len(hits) > _MAX_RAW_METRIC_ROWS
        data["rows"] = hits[:_MAX_RAW_METRIC_ROWS]
        data["count"] = len(hits)
        data["truncated"] = truncated
        msg = f"{len(hits)} finding line(s) mentioning {label}"
        return tool_result_payload(True, msg, data=data)

    if metric_id == AI_RAW_METRIC_PRIORITY:
        by_mk = getattr(trace, "priority_episodes_by_mk", None) or getattr(
            trace, "priorityEpisodesByMk", None)
        eps: List[Any] = []
        if isinstance(by_mk, dict):
            eps = list(by_mk.get(mk) or [])
        elif by_mk is not None and hasattr(by_mk, "get"):
            eps = list(by_mk.get(mk) or [])
        if not eps:
            all_eps = getattr(trace, "priority_episodes", None) or getattr(
                trace, "priorityEpisodes", None) or []
            for ep in all_eps:
                ep_mk = getattr(ep, "mk", None) or (ep.get("mk") if isinstance(ep, dict) else "")
                if ep_mk == mk:
                    eps.append(ep)
        rows = []
        for ep in eps:
            start = getattr(ep, "start_ns", None)
            stop = getattr(ep, "stop_ns", None)
            if start is None and isinstance(ep, dict):
                start, stop = ep.get("startNs"), ep.get("stopNs")
            if not _overlaps_range(start, stop, lo, hi):
                continue
            inherited = bool(getattr(ep, "inherited", None) if not isinstance(ep, dict)
                             else ep.get("inherited"))
            suspect = bool(getattr(ep, "inversion_suspect", None) if not isinstance(ep, dict)
                           else ep.get("inversionSuspect"))
            pattern = getattr(ep, "pattern", None) if not isinstance(ep, dict) else ep.get("pattern")
            base = getattr(ep, "base_pri", None) if not isinstance(ep, dict) else ep.get("basePri")
            peak = getattr(ep, "peak_pri", None) if not isinstance(ep, dict) else ep.get("peakPri")
            rows.append({
                "start": start,
                "stop": stop,
                "duration": (None if start is None or stop is None else int(stop) - int(start)),
                "base_pri": base,
                "peak_pri": peak,
                "inherited": inherited,
                "inversion_suspect": suspect,
                "medium_tasks": _medium_labels(ep),
                "pattern": pattern or "",
            })
        truncated = len(rows) > _MAX_RAW_METRIC_ROWS
        data["episodes"] = rows[:_MAX_RAW_METRIC_ROWS]
        data["count"] = len(rows)
        data["truncated"] = truncated
        msg = f"{len(rows)} priority inheritance episode(s) for {label}"
        return tool_result_payload(True, msg, data=data)

    if metric_id == AI_RAW_METRIC_EXECUTION:
        segs = _segs_for_mk(trace, mk)
        samples = []
        total = 0
        max_dur = 0
        max_at = None
        for seg in segs:
            start = getattr(seg, "start", None) if not isinstance(seg, dict) else seg.get("start")
            end = getattr(seg, "end", None) if not isinstance(seg, dict) else seg.get("end")
            core = getattr(seg, "core", None) if not isinstance(seg, dict) else seg.get("core")
            if not _overlaps_range(start, end, lo, hi):
                continue
            dur = int(end) - int(start) if start is not None and end is not None else 0
            if lo is not None and hi is not None and start is not None and end is not None:
                clip_lo = max(int(start), int(lo))
                clip_hi = min(int(end), int(hi))
                dur = max(0, clip_hi - clip_lo)
            total += dur
            if dur >= max_dur:
                max_dur = dur
                max_at = start
            samples.append({
                "start": start, "stop": end, "duration": dur, "core": core or "",
            })
        truncated = len(samples) > _MAX_RAW_METRIC_ROWS
        data.update({
            "count": len(samples),
            "total": total,
            "max": max_dur,
            "max_at": max_at,
            "mean": (total / len(samples)) if samples else 0,
            "slices": samples[:_MAX_RAW_METRIC_ROWS],
            "truncated": truncated,
        })
        msg = f"{len(samples)} execution slice(s) for {label}"
        return tool_result_payload(True, msg, data=data)

    if metric_id == AI_RAW_METRIC_MIGRATIONS:
        by_mk = getattr(trace, "migrations_by_mk", None) or getattr(
            trace, "migrationsByMk", None)
        migs: List[Any] = []
        if isinstance(by_mk, dict):
            migs = list(by_mk.get(mk) or [])
        elif by_mk is not None and hasattr(by_mk, "get"):
            migs = list(by_mk.get(mk) or [])
        if not migs:
            for m in getattr(trace, "migrations", None) or []:
                m_mk = getattr(m, "merge_key", None) or getattr(m, "mergeKey", None)
                if isinstance(m, dict):
                    m_mk = m.get("merge_key") or m.get("mergeKey")
                if m_mk == mk:
                    migs.append(m)
        rows = []
        for m in migs:
            ns = getattr(m, "ns", None) if not isinstance(m, dict) else m.get("ns")
            if not _in_time_range(ns, lo, hi):
                continue
            src = getattr(m, "from_core", None) if not isinstance(m, dict) else (
                m.get("from_core") or m.get("fromCore"))
            dst = getattr(m, "to_core", None) if not isinstance(m, dict) else (
                m.get("to_core") or m.get("toCore"))
            rows.append({"time": ns, "from": src or "", "to": dst or ""})
        truncated = len(rows) > _MAX_RAW_METRIC_ROWS
        data["events"] = rows[:_MAX_RAW_METRIC_ROWS]
        data["count"] = len(rows)
        data["truncated"] = truncated
        msg = f"{len(rows)} migration(s) for {label}"
        return tool_result_payload(True, msg, data=data)

    if metric_id == AI_RAW_METRIC_BLOCKING:
        segs = sorted(
            _segs_for_mk(trace, mk),
            key=lambda s: getattr(s, "start", None) if not isinstance(s, dict) else s.get("start"),
        )
        gaps = []
        for prev, nxt in zip(segs, segs[1:]):
            prev_end = getattr(prev, "end", None) if not isinstance(prev, dict) else prev.get("end")
            nxt_start = getattr(nxt, "start", None) if not isinstance(nxt, dict) else nxt.get("start")
            if prev_end is None or nxt_start is None:
                continue
            gap = int(nxt_start) - int(prev_end)
            if gap <= 0:
                continue
            if not _in_time_range(nxt_start, lo, hi):
                continue
            gaps.append({"time": nxt_start, "gap": gap})
        truncated = len(gaps) > _MAX_RAW_METRIC_ROWS
        max_gap = max((g["gap"] for g in gaps), default=0)
        total_gap = sum(g["gap"] for g in gaps)
        data.update({
            "count": len(gaps),
            "max": max_gap,
            "total": total_gap,
            "gaps": gaps[:_MAX_RAW_METRIC_ROWS],
            "truncated": truncated,
        })
        msg = f"{len(gaps)} blocking gap(s) for {label}"
        return tool_result_payload(True, msg, data=data)

    # sync STI events whose note mentions the task
    sti = getattr(trace, "sti_events", None) or getattr(trace, "stiEvents", None) or []
    aliases = [a.lower() for a in task_lookup_keys(task) + task_lookup_keys(label) if a]
    rows = []
    for ev in sti:
        t = getattr(ev, "time", None) if not isinstance(ev, dict) else ev.get("time")
        if not _in_time_range(t, lo, hi):
            continue
        note = str(getattr(ev, "note", None) if not isinstance(ev, dict) else ev.get("note") or "")
        target = str(getattr(ev, "target", None) if not isinstance(ev, dict) else ev.get("target") or "")
        event = str(getattr(ev, "event", None) if not isinstance(ev, dict) else ev.get("event") or "")
        blob = f"{note} {target} {event}".lower()
        if not any(a in blob for a in aliases):
            continue
        core = getattr(ev, "core", None) if not isinstance(ev, dict) else ev.get("core")
        rows.append({
            "time": t,
            "core": core or "",
            "target": target,
            "event": event,
            "note": note,
        })
    truncated = len(rows) > _MAX_RAW_METRIC_ROWS
    data["events"] = rows[:_MAX_RAW_METRIC_ROWS]
    data["count"] = len(rows)
    data["truncated"] = truncated
    msg = f"{len(rows)} sync STI event(s) for {label}"
    return tool_result_payload(True, msg, data=data)



def investigate_finding(
    findings: Sequence[dict],
    finding_id: str = "",
    *,
    depth: int = 2,
) -> Dict[str, Any]:
    """Return a tool-result payload with an investigation graph."""
    ctx = build_investigate_context(findings, finding_id, depth=depth)
    ok = bool(ctx.get("ok"))
    msg = str(ctx.get("message") or ("ok" if ok else "failed"))
    data = {k: v for k, v in ctx.items() if k not in ("ok", "message")}
    return tool_result_payload(ok, msg, data=data)


def explain_finding_tool(
    findings: Sequence[dict],
    finding_id: str = "",
    *,
    level: str = "technical",
) -> Dict[str, Any]:
    items = enrich_findings_with_ids(findings) if findings else []
    focus = resolve_finding(items, finding_id) if items else None
    from .ai_investigation import _hypotheses_for_finding
    hyps = []
    if focus:
        hyps = _hypotheses_for_finding(
            str(focus.get("title") or ""), str(focus.get("text") or ""),
        )
    payload = explain_finding_payload(focus, level=level, hypotheses=hyps)
    ok = bool(payload.get("ok"))
    msg = str(payload.get("message") or ("ok" if ok else "failed"))
    data = {k: v for k, v in payload.items() if k not in ("ok", "message")}
    return tool_result_payload(ok, msg, data=data)


def interpret_query_tool(
    question: str,
    findings: Optional[Sequence[dict]] = None,
    *,
    cursor_lo: Optional[float] = None,
    cursor_hi: Optional[float] = None,
) -> Dict[str, Any]:
    payload = interpret_investigation_query(
        question, findings=findings, cursor_lo=cursor_lo, cursor_hi=cursor_hi,
    )
    ok = bool(payload.get("ok"))
    msg = str(payload.get("message") or ("ok" if ok else "failed"))
    data = {k: v for k, v in payload.items() if k not in ("ok", "message")}
    return tool_result_payload(ok, msg, data=data)


def validate_experiment_tool(
    expected: Optional[dict] = None,
    actual: Optional[dict] = None,
) -> Dict[str, Any]:
    payload = validate_experiment(expected, actual)
    ok = bool(payload.get("ok"))
    msg = str(payload.get("message") or ("ok" if ok else "failed"))
    data = {k: v for k, v in payload.items() if k not in ("ok", "message")}
    return tool_result_payload(ok, msg, data=data)


def manage_hypotheses_tool(
    findings: Sequence[dict],
    hypothesis_id: str,
    status: str,
    *,
    reason: str = "",
    finding_id: str = "",
) -> Dict[str, Any]:
    ctx = build_investigate_context(findings, finding_id, depth=2)
    hyps = list(ctx.get("hypotheses") or [])
    updated = set_hypothesis_status(hyps, hypothesis_id, status, reason=reason)
    return tool_result_payload(
        True,
        f"Updated hypothesis {hypothesis_id} → {status}",
        data={"hypotheses": updated, "finding": ctx.get("finding")},
    )


def _planner_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
    ok = bool(payload.get("ok"))
    msg = str(payload.get("message") or ("ok" if ok else "failed"))
    data = {k: v for k, v in payload.items() if k not in ("ok", "message")}
    return tool_result_payload(ok, msg, data=data)


def plan_investigation_tool(
    findings: Optional[Sequence[dict]] = None,
    *,
    question: str = "",
    finding_id: str = "",
) -> Dict[str, Any]:
    return _planner_payload(plan_investigation(
        findings, question=question, finding_id=finding_id))


def suggest_scope_tool(
    question: str = "",
    findings: Optional[Sequence[dict]] = None,
    *,
    cursor_lo: Optional[float] = None,
    cursor_hi: Optional[float] = None,
) -> Dict[str, Any]:
    return _planner_payload(suggest_scope(
        question, findings, cursor_lo=cursor_lo, cursor_hi=cursor_hi))


def detect_contradictions_tool(
    findings: Optional[Sequence[dict]] = None,
    *,
    hypothesis: str = "",
    metrics: Optional[dict] = None,
) -> Dict[str, Any]:
    return _planner_payload(detect_contradictions(
        findings, hypothesis=hypothesis, metrics=metrics))


def assess_evidence_sufficiency_tool(
    findings: Optional[Sequence[dict]] = None,
    *,
    tools_run: Optional[Sequence[str]] = None,
) -> Dict[str, Any]:
    return _planner_payload(assess_evidence_sufficiency(
        findings, tools_run=tools_run))


def cluster_findings_tool(findings: Optional[Sequence[dict]] = None) -> Dict[str, Any]:
    return _planner_payload(cluster_findings(findings))


def generate_fingerprint_tool(findings: Optional[Sequence[dict]] = None) -> Dict[str, Any]:
    return _planner_payload(generate_fingerprint(findings))


def find_similar_investigations_tool(
    findings: Optional[Sequence[dict]] = None,
    *,
    history: Optional[Sequence[dict]] = None,
    limit: int = 5,
) -> Dict[str, Any]:
    return _planner_payload(find_similar_investigations(
        findings, history=history, limit=limit))


def regression_localize_tool(
    candidate: Optional[dict] = None,
    baseline: Optional[dict] = None,
    *,
    findings: Optional[Sequence[dict]] = None,
    label_a: str = "A",
    label_b: str = "B",
) -> Dict[str, Any]:
    return _planner_payload(regression_localize(
        candidate, baseline, findings=findings, label_a=label_a, label_b=label_b))


def build_causal_chain_tool(findings: Optional[Sequence[dict]] = None) -> Dict[str, Any]:
    return _planner_payload(build_causal_chain(findings))


def generate_experiment_plan_tool(
    findings: Optional[Sequence[dict]] = None,
    *,
    task: str = "",
    limit: int = 3,
) -> Dict[str, Any]:
    return _planner_payload(generate_experiment_plan(
        findings, task=task, limit=limit))


def record_experiment_outcome_tool(
    *,
    change: str = "",
    predicted: str = "",
    actual: str = "",
    quality: str = "",
    findings: Optional[Sequence[dict]] = None,
) -> Dict[str, Any]:
    return _planner_payload(record_experiment_outcome(
        change=change, predicted=predicted, actual=actual,
        quality=quality, findings=findings))


def score_investigation_metrics_tool(
    findings: Optional[Sequence[dict]] = None,
    *,
    tools_run: Optional[Sequence[str]] = None,
    elapsed_s: Optional[float] = None,
    conclusion: str = "",
    confidence: str = "",
) -> Dict[str, Any]:
    return _planner_payload(score_investigation_tool(
        findings, tools_run=tools_run, elapsed_s=elapsed_s,
        conclusion=conclusion, confidence=confidence))


def analyze_temporal_causality_tool(
    findings: Optional[Sequence[dict]] = None,
    *,
    task: str = "",
) -> Dict[str, Any]:
    return _planner_payload(analyze_temporal_causality(findings, task=task))


def dependency_trace_context(
    trace: Any,
    lo: Optional[float] = None,
    hi: Optional[float] = None,
) -> Dict[str, Any]:
    """Compact sync / preemption / migration / PI records from a loaded trace."""
    empty: Dict[str, Any] = {
        "sync_holds": [],
        "preemptions": [],
        "migrations": [],
        "priority_episodes": [],
    }
    if trace is None:
        return empty
    lo_i = hi_i = None
    try:
        if lo is not None:
            lo_i = int(lo)
        if hi is not None:
            hi_i = int(hi)
    except (TypeError, ValueError):
        lo_i = hi_i = None

    objs = getattr(trace, "sync_objects", None) or getattr(trace, "syncObjects", None) or {}
    values = objs.values() if hasattr(objs, "values") else []
    sync_holds: List[dict] = []
    for obj in values:
        if not isinstance(obj, dict):
            continue
        kind = str(obj.get("kind") or "")
        key = str(obj.get("key") or f"{kind}:{obj.get('ptr') or ''}")
        for h in obj.get("holds") or []:
            if not isinstance(h, dict):
                continue
            start = h.get("start_ns") if h.get("start_ns") is not None else h.get("startNs")
            stop = h.get("stop_ns") if h.get("stop_ns") is not None else h.get("stopNs")
            if not _overlaps_range(start, stop, lo, hi):
                continue
            dur = h.get("duration_ns")
            if dur is None:
                dur = h.get("durationNs") or 0
            sync_holds.append({
                "kind": kind,
                "key": key,
                "holder": str(h.get("holder_label") or h.get("holderLabel") or ""),
                "start_ns": start,
                "stop_ns": stop,
                "duration_ns": dur or 0,
                "signal": bool(h.get("signal")),
            })

    preemptions: List[dict] = []
    try:
        from .parser import _collect_preemption_events, _task_display_name
        agg: Dict[Tuple[str, str], dict] = {}
        repr_map = getattr(trace, "task_repr", None) or {}
        for mk, pre_disp, _t, duration, _seg in _collect_preemption_events(
                trace, lo_i, hi_i):
            raw = repr_map.get(mk, mk) if isinstance(repr_map, dict) else mk
            victim = _task_display_name(raw)
            rec = agg.setdefault(
                (pre_disp, victim),
                {"preemptor": pre_disp, "victim": victim, "count": 0, "weight": 0},
            )
            rec["count"] += 1
            rec["weight"] += int(duration or 0)
        preemptions = sorted(agg.values(), key=lambda r: -r["weight"])[:40]
    except Exception:
        preemptions = []

    migrations: List[dict] = []
    try:
        from .parser import _migrations_in_range, _task_display_name
        repr_map = getattr(trace, "task_repr", None) or {}
        for m in _migrations_in_range(trace, lo_i, hi_i):
            raw = repr_map.get(m.merge_key, m.merge_key) if isinstance(
                repr_map, dict) else m.merge_key
            migrations.append({
                "task": _task_display_name(raw),
                "from_core": getattr(m, "from_core", "") or "",
                "to_core": getattr(m, "to_core", "") or "",
            })
    except Exception:
        migrations = []

    return {
        "sync_holds": sync_holds,
        "preemptions": preemptions,
        "migrations": migrations,
        "priority_episodes": _gather_priority_episodes(trace, lo=lo, hi=hi),
    }


def build_task_dependency_graph_tool(
    findings: Optional[Sequence[dict]] = None,
    *,
    task: str = "",
    edges: Optional[Sequence[dict]] = None,
    sync_holds: Optional[Sequence[dict]] = None,
    preemptions: Optional[Sequence[dict]] = None,
    migrations: Optional[Sequence[dict]] = None,
    priority_episodes: Optional[Sequence[dict]] = None,
) -> Dict[str, Any]:
    return _planner_payload(build_task_dependency_graph(
        findings,
        edges=edges,
        sync_holds=sync_holds,
        preemptions=preemptions,
        migrations=migrations,
        priority_episodes=priority_episodes,
        task=task,
    ))


def decompose_response_time_tool(
    findings: Optional[Sequence[dict]] = None,
    *,
    task: str = "",
) -> Dict[str, Any]:
    return _planner_payload(decompose_response_time(findings, task=task))


def rank_root_causes_tool(
    findings: Optional[Sequence[dict]] = None,
    *,
    hypotheses: Optional[Sequence[dict]] = None,
) -> Dict[str, Any]:
    return _planner_payload(rank_root_causes(findings, hypotheses=hypotheses))


def verify_claim_tool(
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
    return _planner_payload(verify_claim(
        claim, claim_type=claim_type, subject=subject, object=object,
        evidence=evidence, findings=findings,
        cursor_lo=cursor_lo, cursor_hi=cursor_hi))


def challenge_conclusion_tool(
    conclusion: str = "",
    *,
    findings: Optional[Sequence[dict]] = None,
    hypotheses: Optional[Sequence[dict]] = None,
) -> Dict[str, Any]:
    return _planner_payload(challenge_conclusion(
        conclusion, findings=findings, hypotheses=hypotheses))


def investigation_memory_tool(
    action: str = "recall",
    *,
    record: Optional[dict] = None,
    findings: Optional[Sequence[dict]] = None,
    limit: int = 5,
) -> Dict[str, Any]:
    return _planner_payload(investigation_memory(
        action, record=record, findings=findings, limit=limit))


def cluster_incidents_tool(
    findings: Optional[Sequence[dict]] = None,
    *,
    window_ns: float = 1e6,
) -> Dict[str, Any]:
    return _planner_payload(cluster_incidents(findings, window_ns=window_ns))


def close_investigation_tool(
    conclusion: str = "",
    *,
    findings: Optional[Sequence[dict]] = None,
    experiments: Optional[Sequence[dict]] = None,
    confidence: str = "",
) -> Dict[str, Any]:
    return _planner_payload(close_investigation(
        conclusion, findings=findings, experiments=experiments,
        confidence=confidence))


def analyze_distribution_tool(
    values: Optional[Sequence[Any]] = None,
    *,
    findings: Optional[Sequence[dict]] = None,
    metric: str = "",
    source: str = "",
    task: str = "",
    truncated: bool = False,
) -> Dict[str, Any]:
    return _planner_payload(analyze_distribution(
        values, findings=findings, metric=metric, source=source,
        task=task, truncated=truncated))


_DIST_MAX_SAMPLES = 8000
_DIST_METRIC_ALIASES = {
    "execution": "execution",
    "wcet": "execution",
    "cpu": "execution",
    "slices": "execution",
    "blocking": "blocking",
    "block": "blocking",
    "wait": "blocking",
    "latency": "blocking",
    "response": "blocking",
    "priority_inheritance": "priority_inheritance",
    "priority": "priority_inheritance",
    "pi": "priority_inheritance",
    "inherit": "priority_inheritance",
    "tick": "tick",
    "jitter": "tick",
    "period": "tick",
}


def normalize_distribution_metric(metric: str, task: str = "") -> str:
    raw = str(metric or "").strip().lower()
    if raw in ("", "auto"):
        return "execution" if str(task or "").strip() else "tick"
    return _DIST_METRIC_ALIASES.get(
        raw, "execution" if str(task or "").strip() else "tick")


def distribution_trace_context(
    trace: Any,
    task: str = "",
    metric: str = "",
    lo: Optional[float] = None,
    hi: Optional[float] = None,
) -> Dict[str, Any]:
    """Harvest BTF sample values for analyze_distribution (cap 8000)."""
    kind = normalize_distribution_metric(metric, task)
    values: List[float] = []
    resolved = ""
    if kind == "tick":
        times = list(getattr(trace, "tick_sti_times", None) or getattr(
            trace, "tickStiTimes", None) or [])
        prev = None
        for raw in times:
            try:
                t = float(raw)
            except (TypeError, ValueError):
                continue
            if lo is not None and t < lo:
                continue
            if hi is not None and t > hi:
                continue
            if prev is not None and t > prev:
                values.append(t - prev)
                if len(values) >= _DIST_MAX_SAMPLES:
                    break
            prev = t
        return {
            "values": values,
            "metric": kind,
            "source": "btf",
            "truncated": len(values) >= _DIST_MAX_SAMPLES,
            "task": "",
        }

    want = str(task or "").strip()
    if want and trace is not None:
        resolved = resolve_task_key(want, _task_candidates_from_trace(trace)) or ""
    if not resolved:
        return {
            "values": [],
            "metric": kind,
            "source": "btf",
            "truncated": False,
            "task": want,
        }
    try:
        from .parser import _task_merge_key
        mk = _task_merge_key(resolved)
    except Exception:
        mk = resolved
    segs = _segs_for_mk(trace, mk) or _segs_for_mk(trace, resolved)
    if kind == "execution":
        for seg in segs:
            start = getattr(seg, "start", None) if not isinstance(seg, dict) else seg.get("start")
            end = getattr(seg, "end", None) if not isinstance(seg, dict) else seg.get("end")
            if start is None or end is None or not _overlaps_range(start, end, lo, hi):
                continue
            dur = int(end) - int(start)
            if lo is not None and hi is not None:
                dur = max(0, min(int(end), int(hi)) - max(int(start), int(lo)))
            if dur > 0:
                values.append(float(dur))
            if len(values) >= _DIST_MAX_SAMPLES:
                break
    elif kind == "blocking":
        ordered = sorted(
            segs,
            key=lambda s: getattr(s, "start", None) if not isinstance(s, dict) else s.get("start"),
        )
        for prev, nxt in zip(ordered, ordered[1:]):
            prev_end = getattr(prev, "end", None) if not isinstance(prev, dict) else prev.get("end")
            nxt_start = getattr(nxt, "start", None) if not isinstance(nxt, dict) else nxt.get("start")
            if prev_end is None or nxt_start is None:
                continue
            gap = int(nxt_start) - int(prev_end)
            if gap <= 0 or not _in_time_range(nxt_start, lo, hi):
                continue
            values.append(float(gap))
            if len(values) >= _DIST_MAX_SAMPLES:
                break
    elif kind == "priority_inheritance":
        by_mk = getattr(trace, "priority_episodes_by_mk", None) or getattr(
            trace, "priorityEpisodesByMk", None)
        eps: List[Any] = []
        if isinstance(by_mk, dict):
            eps = list(by_mk.get(mk) or [])
        elif by_mk is not None and hasattr(by_mk, "get"):
            eps = list(by_mk.get(mk) or [])
        if not eps:
            all_eps = getattr(trace, "priority_episodes", None) or getattr(
                trace, "priorityEpisodes", None) or []
            for ep in all_eps:
                ep_mk = getattr(ep, "mk", None) or (
                    ep.get("mk") if isinstance(ep, dict) else "")
                if ep_mk == mk:
                    eps.append(ep)
        for ep in eps:
            start = getattr(ep, "start_ns", None)
            stop = getattr(ep, "stop_ns", None)
            if start is None and isinstance(ep, dict):
                start = ep.get("startNs") or ep.get("start_ns")
                stop = ep.get("stopNs") or ep.get("stop_ns")
            if start is None or stop is None or not _overlaps_range(start, stop, lo, hi):
                continue
            dur = int(stop) - int(start)
            if dur > 0:
                values.append(float(dur))
            if len(values) >= _DIST_MAX_SAMPLES:
                break
    return {
        "values": values,
        "metric": kind,
        "source": "btf",
        "truncated": len(values) >= _DIST_MAX_SAMPLES,
        "task": str(resolved),
    }


def periodicity_trace_context(trace: Any, task: str = "") -> Dict[str, Any]:
    """Tick / STI / task-release timestamps from a loaded trace."""
    tick = list(getattr(trace, "tick_sti_times", None) or getattr(
        trace, "tickStiTimes", None) or [])
    sti: List[dict] = []
    for ev in getattr(trace, "sti_events", None) or getattr(trace, "stiEvents", None) or []:
        if isinstance(ev, dict):
            sti.append(ev)
            continue
        sti.append({
            "time": getattr(ev, "time", None),
            "target": getattr(ev, "target", None),
            "event": getattr(ev, "event", None),
            "note": getattr(ev, "note", None),
        })
    releases: List[float] = []
    want = str(task or "").strip()
    if want and trace is not None:
        resolved = resolve_task_key(want, _task_candidates_from_trace(trace))
        if resolved:
            try:
                from .parser import _task_merge_key
                mk = _task_merge_key(resolved)
            except Exception:
                mk = resolved
            for s in _segs_for_mk(trace, mk) or _segs_for_mk(trace, resolved):
                t = getattr(s, "start", None)
                if t is None and isinstance(s, dict):
                    t = s.get("start")
                try:
                    releases.append(float(t))
                except (TypeError, ValueError):
                    continue
    return {"tick_times": tick, "sti_events": sti, "release_times": releases}


def analyze_periodicity_tool(
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
    return _planner_payload(analyze_periodicity(
        times, findings=findings, expected=expected, source=source,
        durations=durations, tick_times=tick_times, sti_events=sti_events,
        release_times=release_times, lo=lo, hi=hi))


def summarize_investigation_context_tool(
    findings: Optional[Sequence[dict]] = None,
    *,
    hypotheses: Optional[Sequence[dict]] = None,
    tools_run: Optional[Sequence[str]] = None,
    conclusion: str = "",
) -> Dict[str, Any]:
    return _planner_payload(summarize_investigation_context(
        findings, hypotheses=hypotheses, tools_run=tools_run,
        conclusion=conclusion))


def _events_from_metric_payload(payload: Dict[str, Any], metric: str, task: str) -> List[dict]:
    data = payload.get("data") if isinstance(payload, dict) else None
    if not isinstance(data, dict):
        return []
    out: List[dict] = []
    if metric == AI_RAW_METRIC_PRIORITY:
        for ep in data.get("episodes") or []:
            t = ep.get("start")
            if t is None:
                continue
            detail = f"PI base={ep.get('base_pri')} peak={ep.get('peak_pri')}"
            if ep.get("inversion_suspect"):
                detail += " inversion_suspect"
            stop = ep.get("stop")
            dur = ep.get("duration")
            if stop is None and t is not None and dur is not None:
                try:
                    stop = float(t) + float(dur)
                except (TypeError, ValueError):
                    stop = None
            out.append({
                "time": t, "kind": "priority", "detail": detail, "task": task,
                "start": t, "stop": stop, "duration": dur,
            })
    elif metric == AI_RAW_METRIC_EXECUTION:
        for sl in data.get("slices") or []:
            t = sl.get("start")
            if t is None:
                continue
            stop = sl.get("stop")
            dur = sl.get("duration")
            if stop is None and t is not None and dur is not None:
                try:
                    stop = float(t) + float(dur)
                except (TypeError, ValueError):
                    stop = None
            out.append({
                "time": t, "kind": "execution",
                "detail": f"dur={sl.get('duration')} core={sl.get('core')}",
                "task": task, "core": sl.get("core") or "",
                "start": t, "stop": stop, "duration": dur,
            })
    elif metric == AI_RAW_METRIC_MIGRATIONS:
        for row in data.get("events") or data.get("migrations") or []:
            t = row.get("time")
            if t is None:
                continue
            to_core = row.get("to") or ""
            out.append({
                "time": t, "kind": "migration",
                "detail": f"{row.get('from')}→{row.get('to')}",
                "task": task, "core": to_core,
            })
    elif metric == AI_RAW_METRIC_BLOCKING:
        for row in data.get("gaps") or []:
            t = row.get("start") or row.get("time")
            if t is None:
                continue
            gap = row.get("duration", row.get("gap"))
            stop = None
            if t is not None and gap is not None:
                try:
                    stop = float(t) + float(gap)
                except (TypeError, ValueError):
                    stop = None
            out.append({
                "time": t, "kind": "blocking",
                "detail": str(gap if gap is not None else "block"),
                "task": task,
                "start": t, "stop": stop, "duration": gap,
            })
    elif metric == AI_RAW_METRIC_SYNC:
        for row in data.get("events") or []:
            t = row.get("time")
            if t is None:
                continue
            out.append({
                "time": t, "kind": "sync",
                "detail": f"{row.get('event')} {row.get('target')} {row.get('note')}".strip(),
                "task": task, "core": row.get("core") or "",
            })
    return out


def correlate_task_events(
    trace: Any,
    task: str,
    *,
    around_time: Optional[float] = None,
    window: float = 0.0,
    lo: Optional[float] = None,
    hi: Optional[float] = None,
    findings_text: str = "",
    annotations: Optional[Sequence[Any]] = None,
) -> Dict[str, Any]:
    """Host helper: query metrics + search, then build a correlation timeline."""
    if trace is None:
        return tool_result_payload(False, "No trace loaded")
    task = str(task or "").strip()
    if not task:
        return tool_result_payload(False, "task is required")
    events: List[dict] = []
    for metric in (
        AI_RAW_METRIC_BLOCKING,
        AI_RAW_METRIC_EXECUTION,
        AI_RAW_METRIC_MIGRATIONS,
        AI_RAW_METRIC_SYNC,
        AI_RAW_METRIC_PRIORITY,
    ):
        payload = query_raw_metric(
            trace, task, metric, lo=lo, hi=hi, findings_text=findings_text,
        )
        if payload.get("ok"):
            events.extend(_events_from_metric_payload(payload, metric, task))
    # Search is optional enrichment — never fail correlate/critical-path when
    # metrics already produced events (Find can throw on odd annotations).
    try:
        search = search_timeline_hits(trace, task, "contains", annotations=annotations)
    except Exception:
        search = {"ok": False}
    if search.get("ok"):
        data = search.get("data") or {}
        for t in data.get("times") or []:
            try:
                events.append({"time": float(t), "kind": "search", "detail": task, "task": task})
            except (TypeError, ValueError):
                continue
    ctx = build_correlation_timeline(
        events, task=task, around_time=around_time, window=float(window or 0),
    )
    ok = bool(ctx.get("ok"))
    msg = str(ctx.get("message") or ("ok" if ok else "failed"))
    data = {k: v for k, v in ctx.items() if k not in ("ok", "message")}
    return tool_result_payload(ok, msg, data=data)


def find_critical_path_task(
    trace: Any,
    task: str,
    *,
    timestamp: Optional[float] = None,
    window: float = 2000.0,
    annotations: Optional[Sequence[Any]] = None,
) -> Dict[str, Any]:
    """Host helper: correlate events, then build a causal critical path."""
    if trace is None:
        return tool_result_payload(False, "No trace loaded")
    task = str(task or "").strip()
    if not task:
        return tool_result_payload(False, "task is required")
    corr = correlate_task_events(
        trace,
        task,
        around_time=timestamp,
        window=float(window or 2000.0),
        annotations=annotations,
    )
    if not corr.get("ok"):
        return corr
    data = corr.get("data") if isinstance(corr.get("data"), dict) else {}
    events = data.get("events") or []
    ctx = build_critical_path(events, task=task, timestamp=timestamp)
    ok = bool(ctx.get("ok"))
    msg = str(ctx.get("message") or ("ok" if ok else "failed"))
    out = {k: v for k, v in ctx.items() if k not in ("ok", "message")}
    out["correlation"] = data.get("correlation")
    return tool_result_payload(ok, msg, data=out)


def detect_anomalies_finding(
    findings: Sequence[dict],
    *,
    limit: int = 10,
) -> Dict[str, Any]:
    ctx = detect_anomalies(findings, limit=limit)
    ok = bool(ctx.get("ok"))
    msg = str(ctx.get("message") or ("ok" if ok else "failed"))
    data = {k: v for k, v in ctx.items() if k not in ("ok", "message")}
    return tool_result_payload(ok, msg, data=data)


def generate_report_finding(
    findings: Sequence[dict],
    *,
    report_type: str = "performance",
    finding_id: str = "",
    compare: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    ctx = generate_structured_report(
        findings, report_type=report_type, focus_id=finding_id, compare=compare,
    )
    ok = bool(ctx.get("ok"))
    msg = str(ctx.get("message") or ("ok" if ok else "failed"))
    data = {k: v for k, v in ctx.items() if k not in ("ok", "message")}
    return tool_result_payload(ok, msg, data=data)


def compare_performance_tabs(
    candidate_summary: Dict[str, Any],
    baseline_summary: Dict[str, Any],
    *,
    label_a: str = "A",
    label_b: str = "B",
) -> Dict[str, Any]:
    snap_a = snapshot_from_summary(candidate_summary or {}, name=label_a)
    snap_b = snapshot_from_summary(baseline_summary or {}, name=label_b)
    ctx = compare_performance_metrics(snap_a, snap_b, label_a=label_a, label_b=label_b)
    ok = bool(ctx.get("ok"))
    msg = str(ctx.get("message") or ("ok" if ok else "failed"))
    data = {k: v for k, v in ctx.items() if k not in ("ok", "message")}
    return tool_result_payload(ok, msg, data=data)


def budget_task_rows_from_findings(findings: Sequence[dict]) -> List[dict]:
    """Build empty metric rows from finding task names (for check_budget)."""
    rows: List[dict] = []
    seen = set()
    for a in (detect_anomalies(findings or [], limit=40).get("anomalies") or []):
        task = str(a.get("task") or "").strip()
        if not task or task in seen:
            continue
        seen.add(task)
        rows.append({"task": task})
    return rows


def check_budget_finding(
    tasks: Optional[Sequence[dict]] = None,
    budgets: Optional[Dict[str, Any]] = None,
    *,
    findings: Optional[Sequence[dict]] = None,
) -> Dict[str, Any]:
    rows = list(tasks or [])
    if not rows:
        rows = budget_task_rows_from_findings(findings or [])
    ctx = check_task_budgets(rows, budgets)
    ok = bool(ctx.get("ok"))
    msg = str(ctx.get("message") or ("ok" if ok else "failed"))
    data = {k: v for k, v in ctx.items() if k not in ("ok", "message")}
    return tool_result_payload(ok, msg, data=data)


def optimize_finding(
    findings: Sequence[dict],
    *,
    limit: int = 5,
) -> Dict[str, Any]:
    ctx = build_optimization_advice(findings, limit=limit)
    ok = bool(ctx.get("ok"))
    msg = str(ctx.get("message") or ("ok" if ok else "failed"))
    data = {k: v for k, v in ctx.items() if k not in ("ok", "message")}
    return tool_result_payload(ok, msg, data=data)


def regression_explain_from_compare(
    compare: Dict[str, Any],
    findings: Optional[Sequence[dict]] = None,
) -> Dict[str, Any]:
    ctx = explain_regression(compare, findings=findings)
    ok = bool(ctx.get("ok"))
    msg = str(ctx.get("message") or ("ok" if ok else "failed"))
    data = {k: v for k, v in ctx.items() if k not in ("ok", "message")}
    return tool_result_payload(ok, msg, data=data)


def investigation_replay_finding(
    findings: Sequence[dict],
    finding_id: str = "",
    *,
    conclusion: str = "",
    tools_run: Optional[Sequence[str]] = None,
    evidence_times: Optional[Sequence[float]] = None,
    plan: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    finding = resolve_finding(findings, finding_id) if findings or finding_id else None
    ctx = build_investigation_replay(
        finding=finding,
        plan=plan,
        tools_run=tools_run,
        conclusion=conclusion,
        evidence_times=evidence_times,
    )
    ok = bool(ctx.get("ok"))
    msg = str(ctx.get("message") or ("ok" if ok else "failed"))
    data = {k: v for k, v in ctx.items() if k not in ("ok", "message")}
    return tool_result_payload(ok, msg, data=data)


def gather_simulation_inputs(
    trace: Any,
    task: str,
    *,
    lo: Optional[float] = None,
    hi: Optional[float] = None,
    findings_text: str = "",
) -> Dict[str, Any]:
    """Collect slices / migrations / blocking / core util for the simulator."""
    slices: List[dict] = []
    migrations: List[dict] = []
    gaps: List[dict] = []
    label = str(task or "").strip()
    if label and trace is not None:
        for metric, key in (
            (AI_RAW_METRIC_EXECUTION, "slices"),
            (AI_RAW_METRIC_MIGRATIONS, "events"),
            (AI_RAW_METRIC_BLOCKING, "gaps"),
        ):
            res = query_raw_metric(
                trace, label, metric, lo=lo, hi=hi, findings_text=findings_text,
            )
            if not res.get("ok"):
                continue
            d = res.get("data") if isinstance(res.get("data"), dict) else {}
            if key == "slices":
                slices = list(d.get("slices") or [])
                label = str(d.get("task") or label)
            elif key == "events":
                migrations = list(d.get("events") or [])
            else:
                gaps = list(d.get("gaps") or [])
    core_utils: List[Any] = []
    if trace is not None:
        try:
            from .parser import _core_util_pct_rows
            lo_i = int(lo) if lo is not None else None
            hi_i = int(hi) if hi is not None else None
            core_utils = list(_core_util_pct_rows(trace, lo_i, hi_i))
        except Exception:
            core_utils = []
    return {
        "task": label,
        "slices": slices,
        "migrations": migrations,
        "blocking_gaps": gaps,
        "core_utils": core_utils,
    }


def what_if_estimate(
    change: str,
    *,
    task: str = "",
    findings: Optional[Sequence[dict]] = None,
    baseline_metrics: Optional[Dict[str, Any]] = None,
    slices: Optional[Sequence[dict]] = None,
    migrations: Optional[Sequence[dict]] = None,
    blocking_gaps: Optional[Sequence[dict]] = None,
    core_utils: Optional[Sequence[Any]] = None,
) -> Dict[str, Any]:
    """Heuristic what-if (slice replay when metrics provided; else keyword)."""
    has_metrics = bool(slices or migrations or blocking_gaps or core_utils)
    if has_metrics:
        ctx = simulate_what_if(
            change=change,
            task=task,
            slices=slices,
            migrations=migrations,
            blocking_gaps=blocking_gaps,
            core_utils=core_utils,
            findings=findings,
        )
    else:
        ctx = estimate_what_if(
            change=change,
            task=task,
            findings=findings,
            baseline_metrics=baseline_metrics,
        )
    ok = bool(ctx.get("ok"))
    msg = str(ctx.get("message") or ("ok" if ok else "failed"))
    data = {k: v for k, v in ctx.items() if k not in ("ok", "message")}
    return tool_result_payload(ok, msg, data=data)


def optimize_experiment_finding(
    *,
    task: str = "",
    findings: Optional[Sequence[dict]] = None,
    slices: Optional[Sequence[dict]] = None,
    migrations: Optional[Sequence[dict]] = None,
    blocking_gaps: Optional[Sequence[dict]] = None,
    core_utils: Optional[Sequence[Any]] = None,
    limit: int = 5,
) -> Dict[str, Any]:
    ctx = run_optimization_experiments(
        task=task,
        slices=slices,
        migrations=migrations,
        blocking_gaps=blocking_gaps,
        core_utils=core_utils,
        findings=findings,
        limit=limit,
    )
    ok = bool(ctx.get("ok"))
    msg = str(ctx.get("message") or ("ok" if ok else "failed"))
    data = {k: v for k, v in ctx.items() if k not in ("ok", "message")}
    return tool_result_payload(ok, msg, data=data)


def analyze_traces_snapshots(
    snapshots: Sequence[Dict[str, Any]],
) -> Dict[str, Any]:
    ctx = analyze_multi_traces(snapshots)
    ok = bool(ctx.get("ok"))
    msg = str(ctx.get("message") or ("ok" if ok else "failed"))
    data = {k: v for k, v in ctx.items() if k not in ("ok", "message")}
    return tool_result_payload(ok, msg, data=data)


def baseline_score_finding(
    snapshot: Dict[str, Any],
    *,
    profile: Optional[Dict[str, Any]] = None,
    task: str = "",
) -> Dict[str, Any]:
    task = str(task or "").strip()
    if task:
        tasks = snapshot.get("tasks") if isinstance(snapshot, dict) else {}
        tasks = tasks if isinstance(tasks, dict) else {}
        snapshot = {"tasks": {k: v for k, v in tasks.items() if k == task}}
    ctx = score_against_baseline(profile, snapshot)
    ok = bool(ctx.get("ok"))
    msg = str(ctx.get("message") or ("ok" if ok else "failed"))
    data = {k: v for k, v in ctx.items() if k not in ("ok", "message")}
    return tool_result_payload(ok, msg, data=data)


def recommend_experiments_finding(
    findings: Sequence[dict],
    *,
    finding_id: str = "",
    task: str = "",
    limit: int = 5,
) -> Dict[str, Any]:
    ctx = recommend_validation_experiments(
        findings, finding_id=finding_id, task=task, limit=limit,
    )
    ok = bool(ctx.get("ok"))
    msg = str(ctx.get("message") or ("ok" if ok else "failed"))
    data = {k: v for k, v in ctx.items() if k not in ("ok", "message")}
    return tool_result_payload(ok, msg, data=data)


def _gather_priority_episodes(
    trace: Any,
    *,
    task: str = "",
    lo: Optional[float] = None,
    hi: Optional[float] = None,
) -> List[dict]:
    """All (or one task's) priority-inheritance episodes as raw dict rows."""
    out: List[dict] = []
    if trace is None:
        return out
    task = str(task or "").strip()
    mk_filter = None
    if task:
        resolved = resolve_task_key(task, _task_candidates_from_trace(trace))
        if not resolved:
            return out
        try:
            from .parser import _task_merge_key
            mk_filter = _task_merge_key(resolved)
        except Exception:
            mk_filter = resolved
    all_eps = getattr(trace, "priority_episodes", None) or getattr(
        trace, "priorityEpisodes", None) or []
    repr_map = getattr(trace, "task_repr", None) or getattr(trace, "taskRepr", None) or {}
    for ep in all_eps:
        mk = getattr(ep, "mk", None) if not isinstance(ep, dict) else ep.get("mk")
        if mk_filter is not None and mk != mk_filter:
            continue
        start = getattr(ep, "start_ns", None) if not isinstance(ep, dict) else ep.get("startNs")
        stop = getattr(ep, "stop_ns", None) if not isinstance(ep, dict) else ep.get("stopNs")
        if not _overlaps_range(start, stop, lo, hi):
            continue
        label = str(repr_map.get(mk) or "") if isinstance(repr_map, dict) else ""
        if not label:
            label = str(mk or "")
        base = getattr(ep, "base_pri", None) if not isinstance(ep, dict) else ep.get("basePri")
        peak = getattr(ep, "peak_pri", None) if not isinstance(ep, dict) else ep.get("peakPri")
        inherited = bool(
            getattr(ep, "inherited", None) if not isinstance(ep, dict) else ep.get("inherited"))
        suspect = bool(
            getattr(ep, "inversion_suspect", None) if not isinstance(ep, dict)
            else ep.get("inversionSuspect"))
        pattern = getattr(ep, "pattern", None) if not isinstance(ep, dict) else ep.get("pattern")
        out.append({
            "task": label,
            "start": start,
            "stop": stop,
            "duration": (None if start is None or stop is None else int(stop) - int(start)),
            "base_pri": base,
            "peak_pri": peak,
            "inherited": inherited,
            "inversion_suspect": suspect,
            "medium_tasks": _medium_labels(ep),
            "pattern": pattern or "",
        })
    return out


def detect_priority_inversion_host(
    trace: Any,
    findings: Optional[Sequence[dict]] = None,
    *,
    task: str = "",
    window: Optional[float] = None,
    lo: Optional[float] = None,
    hi: Optional[float] = None,
) -> Dict[str, Any]:
    """Host helper: gather PI episodes (optionally scoped to a task) and detect inversions."""
    if trace is None:
        return tool_result_payload(False, "No trace loaded")
    episodes = _gather_priority_episodes(trace, task=task, lo=lo, hi=hi)
    ctx = detect_priority_inversion(episodes, findings, task=task, window=window)
    ok = bool(ctx.get("ok"))
    msg = str(ctx.get("message") or ("ok" if ok else "failed"))
    data = {k: v for k, v in ctx.items() if k not in ("ok", "message")}
    return tool_result_payload(ok, msg, data=data)


def find_related_findings_finding(
    findings: Sequence[dict],
    *,
    finding_id: str = "",
    task: str = "",
    metric: str = "",
    window: Optional[float] = None,
    limit: int = 10,
) -> Dict[str, Any]:
    ctx = find_related_findings(
        findings, finding_id=finding_id, task=task, metric=metric,
        window=window, limit=limit,
    )
    ok = bool(ctx.get("ok"))
    msg = str(ctx.get("message") or ("ok" if ok else "failed"))
    data = {k: v for k, v in ctx.items() if k not in ("ok", "message")}
    return tool_result_payload(ok, msg, data=data)


_COMPARE_TASKS_METRICS: Tuple[str, ...] = (
    AI_RAW_METRIC_EXECUTION,
    AI_RAW_METRIC_BLOCKING,
    AI_RAW_METRIC_MIGRATIONS,
    AI_RAW_METRIC_PRIORITY,
)


def compare_tasks_host(
    trace: Any,
    task_a: str,
    task_b: str,
    *,
    metrics: Optional[Sequence[str]] = None,
    lo: Optional[float] = None,
    hi: Optional[float] = None,
    findings_text: str = "",
) -> Dict[str, Any]:
    """Host helper: query execution/blocking/migrations/priority for both tasks."""
    if trace is None:
        return tool_result_payload(False, "No trace loaded")
    task_a = str(task_a or "").strip()
    task_b = str(task_b or "").strip()
    if not task_a or not task_b:
        return tool_result_payload(False, "task_a and task_b must be non-empty strings")
    wanted = [
        m for m in (normalize_raw_metric(x) for x in (metrics or ()))
        if m in _COMPARE_TASKS_METRICS
    ]
    if not wanted:
        wanted = list(_COMPARE_TASKS_METRICS)
    label_a = task_a
    label_b = task_b
    data_a: Dict[str, Any] = {}
    data_b: Dict[str, Any] = {}
    for metric in wanted:
        res_a = query_raw_metric(trace, task_a, metric, lo=lo, hi=hi, findings_text=findings_text)
        if res_a.get("ok"):
            d = res_a.get("data") if isinstance(res_a.get("data"), dict) else {}
            data_a[metric] = d
            label_a = str(d.get("task") or label_a)
        res_b = query_raw_metric(trace, task_b, metric, lo=lo, hi=hi, findings_text=findings_text)
        if res_b.get("ok"):
            d = res_b.get("data") if isinstance(res_b.get("data"), dict) else {}
            data_b[metric] = d
            label_b = str(d.get("task") or label_b)
    ctx = compare_tasks_metrics(label_a, label_b, data_a, data_b, metrics=wanted)
    ok = bool(ctx.get("ok"))
    msg = str(ctx.get("message") or ("ok" if ok else "failed"))
    data = {k: v for k, v in ctx.items() if k not in ("ok", "message")}
    return tool_result_payload(ok, msg, data=data)
