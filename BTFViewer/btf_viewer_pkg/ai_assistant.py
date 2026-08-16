"""Diagnostic assistant for BTF Viewer (any OpenAI-compatible endpoint).

Sends structured Analysis Findings (and optional scoped metrics) to a chat
endpoint — never the raw BTF event stream.
"""
from __future__ import annotations

import datetime
import html
import json
import os
import re
import ssl
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

from ._imports import *  # noqa: F403,F401
from .config import _svg_icon, rasterize_svg_pixmap
from .ai_mermaid import (
    _link_row_html,
    decode_mermaid_zoom_token,
    hit_test_mermaid,
    mermaid_block_html,
    mermaid_to_svg,
)
from .ai_tools import (
    AI_TOOL_EXPORT_INVESTIGATION,
    AI_TOOL_EXPORT_REPORT,
    AI_TOOL_SYSTEM_ADDENDUM,
    ai_viewer_tools,
    btf_highlight_href,
    btf_jump_href,
    btf_range_href,
    build_ai_report_csv,
    build_ai_report_html,
    canonical_assistant_tool_message,
    ensure_gemini_thought_signatures,
    extract_tool_calls,
    empty_chat_completion_error,
    format_tool_result_content,
    is_export_tool,
    is_query_tool,
    max_tool_rounds,
    merge_tool_calls,
    assistant_message_text,
    needs_gemini_thought_signatures,
    normalize_tool_chat_messages,
    parse_ai_auto_apply,
    parse_ai_mcp_log,
    parse_btf_highlight_href,
    parse_btf_jump_href,
    parse_btf_range_href,
    parse_tool_calls_from_text,
    strip_parsed_tool_markup,
    summarise_tool_call,
    tool_batch_auto_runs,
    tool_result_message,
    tool_result_payload,
    validate_tool_call,
)
from .ai_investigation import (
    EVIDENCE_PANEL_TOOLS,
    build_investigation_package,
    complete_investigation_plan,
    default_investigation_plan,
    evidence_panel_labels,
    extract_evidence_panel_payload,
    format_evidence_panel_markdown,
    format_investigation_plan_status,
    investigation_tree_mermaid,
    is_agent_template,
    mark_plan_steps_from_tools,
    parse_btf_exp_href,
    parse_btf_hyp_href,
    parse_btf_scope_href,
    parse_btf_tool_href,
)
from .ai_case import (
    INVESTIGATION_MODE_LABELS,
    INVESTIGATION_MODES,
    accumulate_cost,
    build_validation_catalog,
    builtin_investigation_templates,
    chat_usage_from_response,
    apply_cloud_privacy,
    apply_experiment_to_hypotheses,
    CAPABILITY_CHAT_PROBE,
    classify_trace_privacy,
    clamp_ai_split_bottom,
    compare_hypotheses,
    dump_user_historical_knowledge,
    dump_user_investigation_templates,
    empty_cost_meter,
    format_capability_report,
    format_confidence_evolution,
    format_cost_meter,
    format_cost_status,
    format_privacy_chip,
    historical_knowledge_for_finding,
    capability_probe_body,
    infer_model_capability,
    interpret_investigation_query,
    merge_live_capability,
    should_confirm_interpreted_query,
    tool_calling_from_chat_response,
    investigation_mode_plan,
    investigation_mode_prompt,
    interpreted_run_prompt,
    investigation_template_prompt,
    new_user_historical_entry,
    new_user_investigation_template,
    parse_user_historical_knowledge,
    parse_user_investigation_templates,
    toggle_interpreted_scope,
    set_hypothesis_status,
    update_case_from_tool,
    validate_ai_response,
    VALIDATE_EXPERIMENT_PROMPT,
)
from .html_report import btf_html_report_document


class OllamaCancelled(Exception):
    """User stopped an in-flight AI request."""


AI_MCP_LOG_FILENAME = "ai_mcp_messages.log"
_MCP_LOG_LOCK = threading.Lock()
_MCP_LOG_ENABLED = False


def ai_mcp_log_path() -> str:
    """Path for the optional MCP message debug log (process current directory)."""
    return os.path.join(os.getcwd(), AI_MCP_LOG_FILENAME)


def set_ai_mcp_log_enabled(enabled: bool) -> None:
    """Enable/disable MCP debug logging for all AI HTTP activity."""
    global _MCP_LOG_ENABLED
    with _MCP_LOG_LOCK:
        _MCP_LOG_ENABLED = bool(enabled)


def is_ai_mcp_log_enabled() -> bool:
    return bool(_MCP_LOG_ENABLED)


def _want_ai_mcp_log(explicit: bool = False) -> bool:
    return bool(explicit) or is_ai_mcp_log_enabled()


def append_ai_mcp_log(
    kind: str,
    data: Any,
    *,
    path: Optional[str] = None,
) -> None:
    """Append one MCP request/response record to the debug log file."""
    dest = path or ai_mcp_log_path()
    stamp = datetime.datetime.now().astimezone().isoformat(timespec="milliseconds")
    label = str(kind or "message").strip() or "message"
    try:
        body = json.dumps(data, ensure_ascii=False, indent=2, default=str)
    except Exception:
        body = repr(data)
    block = f"======== {stamp} {label} ========\n{body}\n\n"
    with _MCP_LOG_LOCK:
        with open(dest, "a", encoding="utf-8") as fh:
            fh.write(block)


def _log_ai_mcp(kind: str, data: Any, *, enabled: bool) -> None:
    if not enabled:
        return
    try:
        append_ai_mcp_log(kind, data)
    except Exception:
        pass


class _MermaidZoomDialog(QDialog):
    """Larger view of an AI mermaid diagram (scroll to zoom)."""

    def __init__(
        self,
        source: str,
        parent=None,
        *,
        on_link: Optional[Callable[[QUrl], None]] = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Diagram")
        self.setModal(True)
        self._source = source or ""
        self._svg = mermaid_to_svg(self._source, interactive=False)
        self._scale = 2.0
        self._hit_scale = 2.0
        lay = QVBoxLayout(self)
        hint = QLabel(
            "Scroll to zoom. Click a task/core in the figure or a name below."
        )
        hint.setStyleSheet("color:#8b98a8;font-size:11px;")
        hint.setWordWrap(True)
        lay.addWidget(hint)
        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(False)
        self._scroll.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._img = QLabel()
        self._img.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._img.setCursor(Qt.CursorShape.PointingHandCursor)
        self._on_link = on_link
        self._scroll.setWidget(self._img)
        self._scroll.viewport().installEventFilter(self)
        self._img.installEventFilter(self)
        lay.addWidget(self._scroll, 1)
        links_html = _link_row_html(self._source)
        if links_html:
            links = QTextBrowser()
            links.setOpenExternalLinks(False)
            links.setOpenLinks(False)
            links.setMaximumHeight(80)
            links.setHtml(
                f"<html><body style=\"background:#12161d;color:#dbe2ea;\">"
                f"{links_html}</body></html>"
            )
            if on_link:
                links.anchorClicked.connect(on_link)
            lay.addWidget(links)
        close = QPushButton("Close")
        close.clicked.connect(self.accept)
        lay.addWidget(close, 0, Qt.AlignmentFlag.AlignRight)
        self._render()
        pm = self._img.pixmap()
        pw = pm.width() if pm and not pm.isNull() else 480
        ph = pm.height() if pm and not pm.isNull() else 280
        self.resize(min(960, max(480, pw + 48)), min(720, max(360, ph + 160)))

    def eventFilter(self, obj, event):  # noqa: N802
        if obj is self._scroll.viewport() and event.type() == QEvent.Type.Wheel:
            delta = event.angleDelta().y()
            if delta:
                factor = 1.15 if delta > 0 else 1.0 / 1.15
                self._scale = max(0.5, min(6.0, self._scale * factor))
                self._render()
                return True
        if obj is self._img and event.type() == QEvent.Type.MouseButtonPress:
            if event.button() == Qt.MouseButton.LeftButton and self._on_link:
                pos = event.position().toPoint() if hasattr(event, "position") else event.pos()
                hit = hit_test_mermaid(
                    self._source, pos.x(), pos.y(), scale=self._hit_scale)
                if hit:
                    kind, value = hit
                    if kind == "jump":
                        self._on_link(QUrl(btf_jump_href(value)))
                    else:
                        self._on_link(QUrl(btf_highlight_href(value)))
                    return True
        return QDialog.eventFilter(self, obj, event)

    def _render(self) -> None:
        if not self._svg:
            self._img.setText("Could not render diagram.")
            return
        pm, hit_scale = rasterize_svg_pixmap(
            self._svg, scale=self._scale, fill=QColor("#12161d"))
        if pm.isNull():
            self._img.setText("Could not render diagram.")
            return
        self._hit_scale = hit_scale
        self._img.setPixmap(pm)
        self._img.resize(pm.size())



# Alias used by newer call sites; same exception.
AiCancelled = OllamaCancelled
AI_SYSTEM_PROMPT = (
    "You are an expert Real-Time Operating System (RTOS) and SMP trace analysis "
    "assistant for FreeRTOS BTF traces. Analyse the provided structured metrics "
    "and answer the user's diagnostic question clearly. Focus on root causes "
    "(preemption, priority inversion, lock contention, core thrashing, switch "
    "overhead, tick health). Prefer concrete task names, cores, and durations. "
    "When recommending a next UI check, name the Statistics page "
    "(Timeline Anomalies, Worst Events, Response Time, Critical Path, "
    "Period / Jitter, Unified Jitter, Recurring Patterns, Task Health, "
    "Task × Core, Core Utilization Over Time, Preemption Matrix, "
    "Waiter × Owner, Mutex Blocking, or the matching metric table) and that "
    "p95/p99 cells are clickable. Explain distributions with p50 / p99 / CV, "
    "not only Max. When comparing scopes, say which window the numbers come "
    "from. Summarise only from cited evidence. Set confidence from coverage "
    "(High when the scoped tables contain the cited metric; Low when the "
    "window is empty or the metric is missing). "
    "When mentioning a time, write it as jump:TIME where TIME is the numeric "
    "value in the trace time unit (e.g. jump:1805120). "
    "For every important conclusion, cite evidence (metric names, counts, "
    "jump:TIME ranges) and state confidence as High, Medium, or Low — and "
    "whether the evidence is Directly observed, Strong correlation, Possible "
    "explanation, or Insufficient evidence. Do not invent numbers, task names, "
    "or jump:TIME timestamps that are not in the findings, tool results, or "
    "Trace Compare tables. If a Cursor region window is listed, only cite "
    "jump:TIME values inside that window (or say the window has no matching "
    "evidence). Keep answers concise. "
    + AI_TOOL_SYSTEM_ADDENDUM
)

# Preferred reply language (Settings → AI / Language… dialog). Keep in sync with web.
DEFAULT_AI_RESPONSE_LANGUAGE = "English"
AI_RESPONSE_LANGUAGES: Tuple[str, ...] = (
    "English",
    "Traditional Chinese (繁體中文)",
    "Simplified Chinese (简体中文)",
    "Japanese (日本語)",
    "Korean (한국어)",
    "German",
    "French",
    "Spanish",
)


def build_ai_system_prompt(
    response_language: str = DEFAULT_AI_RESPONSE_LANGUAGE,
) -> str:
    """System prompt with an explicit reply-language instruction."""
    lang = (response_language or DEFAULT_AI_RESPONSE_LANGUAGE).strip() or DEFAULT_AI_RESPONSE_LANGUAGE
    return (
        f"{AI_SYSTEM_PROMPT} Always write your entire reply in {lang}."
    )

# (id, label, prompt) — keep in sync with web/src/utils/ollamaClient.js
AI_COMPARE_TEMPLATE_ID = "compare"

# Templates that only make sense for a multi-core (SMP) trace — keep in sync
# with web/src/utils/ollamaClient.js AI_SMP_ONLY_TEMPLATE_IDS.
AI_SMP_ONLY_TEMPLATE_IDS = frozenset({"migrations", "balance"})

AI_TEMPLATE_QUESTIONS: Tuple[Tuple[str, str, str], ...] = (
    (
        "findings",
        "Analysis Findings",
        "Walk through the Analysis Findings in the context. For each finding, "
        "state its severity, what it means for this RTOS/SMP system, and which "
        "Statistics section or timeline check to open next "
        "(Timeline Anomalies, Worst Events, Response Time, Critical Path, "
        "Task Health, Period / Jitter, Unified Jitter, Recurring Patterns, "
        "Task × Core, Core Utilization Over Time, Preemption Matrix, "
        "Waiter × Owner, Mutex Blocking, or the matching metric table). If there "
        "are no findings, say so and suggest a default top-down order: "
        "Timeline Anomalies → Worst Events → Response Time → Critical Path → "
        "Task Health → Period / Jitter → Unified Jitter → "
        "Execution / Blocking tails.",
    ),
    (
        "investigate",
        "Investigate",
        "Investigate the main performance problem in this scope. First call "
        "investigate() to get hypotheses and an evidence chain, then use "
        "query_raw_metric and search_timeline as needed. Call "
        "build_task_dependency_graph (optional task) and "
        "analyze_temporal_causality for the wait/preempt/migrate chain. "
        "Call rank_root_causes then challenge_conclusion. "
        "Place cursors and "
        "zoom_to_range on the strongest evidence, highlight the key task, "
        "name the Statistics page to open next (Timeline Anomalies, Worst "
        "Events, Response Time, Critical Path, Task Health, Period / Jitter, "
        "Unified Jitter, Recurring Patterns, Task × Core, Core Utilization "
        "Over Time, Preemption Matrix, Waiter × Owner, or Mutex Blocking), "
        "and finish with: (1) goal, (2) numbered investigation steps you "
        "took, (3) root cause with confidence, (4) clickable jump:TIME "
        "evidence, (5) next mitigation to try.",
    ),
    (
        "root_cause",
        "Root cause",
        "Perform root-cause analysis for the top finding. Call "
        "investigate(finding_id) first, then follow the chain "
        "deadline/WCET → execution → preemption → blocking → mutex → "
        "priority inheritance → migration only as far as the evidence "
        "supports. Call build_task_dependency_graph and "
        "analyze_temporal_causality on the victim task. Call "
        "rank_root_causes then challenge_conclusion. Call "
        "query_raw_metric / search_timeline when numbers are "
        "missing. Set cursors around the worst episode, highlight the "
        "victim task, name Timeline Anomalies or Worst Events when a tail "
        "spike is the evidence, and answer with Root cause, Evidence (bullet list with "
        "jump:TIME), Confidence, and Suggested fix.",
    ),
    (
        "verify",
        "Verify finding",
        "Verify the selected Analysis Finding. Call investigate(finding_id=ID) "
        "first (use the finding_id given in the user message). Then collect "
        "evidence with query_raw_metric / correlate_events / search_timeline as "
        "needed. Call verify_claim on the finding statement and "
        "challenge_conclusion to list alternatives. Place cursors and "
        "zoom_to_range on the strongest evidence. Name the Statistics page "
        "to open next. "
        "Finish with a verdict: Confirmed, Rejected, or Inconclusive; list "
        "Evidence as jump:TIME bullets; Confidence (High/Medium/Low); "
        "Alternatives considered; and one next check.",
    ),
    (
        "explain_region",
        "Explain region",
        "Explain the current timeline cursor region (scope C1–Cn — see the "
        "Cursor region window in context). Stay strictly inside that window: "
        "every jump:TIME you cite must fall between C1 and Cn. Identify "
        "longest blocking, migrations, priority changes, wakeups, mutex "
        "contention, deadline issues, idle gaps, and CPU imbalance in this "
        "window. Check in-window Timeline Anomalies and Worst Events. Call "
        "correlate_events and query_raw_metric as needed. Use "
        "only in-window jump:TIME evidence (or state that tools found none). "
        "End with: Summary, Top issues, Evidence, Suggested next action.",
    ),
    (
        AI_COMPARE_TEMPLATE_ID,
        "Trace Compare",
        "Compare Trace A vs Trace B using the Trace Compare tables in the "
        "context. Classify each major delta as Regression, Improvement, or "
        "Neutral (CPU, migrations, latency, tick health, sync). State which "
        "side is worse for each concern, the likely cause with confidence, "
        "and which Statistics section or Trace Compare page to open next. "
        "Mention the Compare summary strip under the scope checkbox when "
        "A vs B deltas are already summarised there, including the Why? "
        "line computed from those deltas. "
        "Use jump:TIME when a concrete timestamp is available.",
    ),
    (
        "triage",
        "Triage findings",
        "Summarise the Analysis Findings and list the top three issues to "
        "investigate first, with the Statistics section to open for each "
        "(Timeline Anomalies, Worst Events, Response Time, Critical Path, "
        "Task Health, Period / Jitter, Unified Jitter, Recurring Patterns, "
        "Task × Core, Core Utilization Over Time, Preemption Matrix, "
        "Waiter × Owner, Mutex Blocking, or the matching metric table).",
    ),
    (
        "task_profile",
        "Task profile",
        "Build an AI task behaviour profile for the hottest or most "
        "problematic task in the findings (CPU %, typical / p95 / WCET "
        "execution, dispatch, blocking, migrations, sync / priority "
        "inheritance). Use query_raw_metric if needed. Call "
        "analyze_distribution (metric auto or execution) for p50 / p90 / "
        "p99 / CV / outlier rate. Call "
        "decompose_response_time for that task; treat the shares as relative "
        "magnitudes, not cycle-accurate milliseconds. Name Period / Jitter, "
        "Unified Jitter, Response Time, Task Health, and Task × Core when they "
        "apply. Tell the engineer they "
        "can click Execution / Blocking / Inter-arrival p95 or p99 to jump. "
        "End with a short "
        "assessment checklist (normal / warning) and one Ask-next question.",
    ),
    (
        "diagnostic_report",
        "Diagnostic report",
        "Write a structured engineering diagnostic report for this scope: "
        "Executive summary, Key findings, CPU / scheduling, WCET / "
        "deadlines, Blocking / sync, Migrations, Task × Core, Timeline "
        "Anomalies / Worst Events, Response Time, Critical Path, Period / "
        "Jitter, Unified Jitter, Recurring Patterns, Task Health, Waiter × "
        "Owner, Mutex Blocking, Preemption Matrix, Core Utilization Over Time, "
        "Root cause, "
        "Recommendations (only when evidence supports them), and Evidence "
        "timeline with jump:TIME links. Use export_report when the user "
        "asks to save the report.",
    ),
    (
        "what_if",
        "What-if",
        "Call what_if with a concrete change (pin TASK to Core_N, raise "
        "priority, reduce mutex contention). The tool runs a heuristic "
        "slice-replay simulator (not FreeRTOS kernel). Summarise baseline vs "
        "simulated migrations/blocking/load-balance and the labelled "
        "disclaimer. Cite evidence; do not invent numbers beyond the tool.",
    ),
    (
        "optimize",
        "Optimize",
        "Call optimize_experiment for the hottest task (pin / priority / "
        "contention / migration candidates), then summarise the ranked "
        "experiments and best cost delta. Optionally call optimize for "
        "qualitative mitigations. Label results as heuristic estimates — not "
        "measured FreeRTOS behavior. Call investigate() if the top finding "
        "is unclear.",
    ),
    (
        "latency",
        "Highest latency",
        "Which tasks show the highest latency or blocking? Explain likely "
        "causes using preemption, dispatch latency, and mutex evidence in "
        "the context. Open Worst Events, Response Time, Critical Path, "
        "Mutex Blocking, and Waiter × Owner "
        "(heuristic mutex handoff — not a kernel wait queue). Click Blocking "
        "p95/p99 to jump. Call analyze_distribution (metric blocking or auto) "
        "for the worst-task tail. Call decompose_response_time for the "
        "worst task; treat shares as relative, not measured milliseconds.",
    ),
    (
        "wcet",
        "WCET / hot CPU",
        "Which tasks dominate CPU and which have the worst execution-slice "
        "Max? Call analyze_distribution (metric execution) on the hottest "
        "task and cite p50 / p99 / CV, not only Max. Open Timeline Anomalies, "
        "Worst Events, Response Time, Period / Jitter, Unified Jitter, and "
        "Task Health. Click Execution Max / "
        "p95 / p99 to jump. Recommend whether to "
        "affinity-pin, reduce fan-out, or inspect preemption.",
    ),
    (
        "migrations",
        "Migration thrash",
        "Is there core thrashing or lock-bounce? Cite migration rate, ping, "
        "dwell, and any hot mutex/queue bounces. Suggest affinity or "
        "ownership fixes. Open Task × Core, Core Utilization Over Time, and "
        "Timeline Anomalies migration bursts.",
    ),
    (
        "balance",
        "Core balance",
        "Is SMP load balance healthy? Interpret Load Balance Score / σ and "
        "whether Concurrent Core Active or Switch Overhead needs attention. "
        "Open Task × Core for per-task per-core share of the scoped span.",
    ),
    (
        "tick",
        "Tick health",
        "Interpret Trace Health (TICK). Are large gaps expected under "
        "tickless idle, or should we re-check inside a busy cursor window? "
        "Call analyze_periodicity (source auto or tick) and report expected "
        "vs p50/p99/max, RMS jitter, and kind. Do not conflate this with "
        "Period / Jitter — that page is task inter-arrival, not the tick "
        "source.",
    ),
    (
        "priority",
        "Priority inversion",
        "Is there priority inversion or L/M/H geometry? Explain any inherit "
        "episodes and what to verify next. If mutex handoff is in play, open "
        "Waiter × Owner (heuristic next-acquirer × previous-holder, not a "
        "kernel wait queue).",
    ),
    (
        "deadlines",
        "Deadline / budget",
        "Are there deadline or CPU-budget concerns in the findings? What "
        "should the engineer measure next? Open the Task Health deadline "
        "band (click the band to jump to Deadlines).",
    ),
    (
        "explain_finding",
        "Explain finding",
        "Explain the selected Analysis Finding. Call explain_finding("
        "finding_id=ID, level=LEVEL) first (use finding_id and level= from "
        "the user message; levels: quick, technical, deep; default "
        "technical). Then add jump:TIME "
        "evidence from investigate or correlate_events if the explanation "
        "is still thin. Finish with: Summary, What it means, Evidence, "
        "What would disprove this, and one next check that names the "
        "Statistics page to open.",
    ),
    (
        "auto_investigate",
        "Auto investigate",
        "Automatically investigate and confirm the top finding end-to-end. "
        "Call investigate(finding_id) first, then correlate_events on the "
        "same window. Call find_critical_path to build the causal chain, or "
        "detect_priority_inversion instead when investigate flags a "
        "priority-inversion finding. Call build_task_dependency_graph and "
        "analyze_temporal_causality on the same task. Call "
        "rank_root_causes then challenge_conclusion. Place cursors and "
        "zoom_to_range on the strongest evidence (Apply cursors; cite "
        "range:LO/HI or btfrange:LO/HI when the critical path has a window). "
        "Name Timeline Anomalies or Worst Events as the next UI check. "
        "Then call what_if or "
        "optimize_experiment to "
        "test a concrete mitigation. Finish with a verdict — Confirmed, "
        "Rejected, or Inconclusive — Evidence as jump:TIME bullets, "
        "Confidence (High/Medium/Low), and one recommended experiment to "
        "run next.",
    ),
)

# Always-visible wrapping chips. Keep in sync with web/src/utils/ollamaClient.js.
# Last primary id shares a row with More templates… (web `.ai-tpl-row`).
AI_TEMPLATE_PRIMARY_IDS: Tuple[str, ...] = (
    "investigate",
    "findings",
    "explain_region",
    "auto_investigate",
)


def ai_template_primary_rows(
    ids: Optional[Tuple[str, ...]] = None,
) -> Tuple[Tuple[str, ...], Tuple[str, ...]]:
    """Split primary chips so Auto investigate + More sit on the last row."""
    seq = tuple(ids if ids is not None else AI_TEMPLATE_PRIMARY_IDS)
    if len(seq) <= 1:
        return seq, ()
    return seq[:-1], seq[-1:]

# Overflow menu groups for the remaining templates (ids must cover every
# AI_TEMPLATE_QUESTIONS entry that is not in AI_TEMPLATE_PRIMARY_IDS).
AI_TEMPLATE_MENU_GROUPS: Tuple[Tuple[str, Tuple[str, ...]], ...] = (
    ("Diagnose", ("root_cause", "verify", "explain_finding", "triage", "diagnostic_report")),
    ("Compare", (AI_COMPARE_TEMPLATE_ID,)),
    (
        "Metrics",
        (
            "task_profile",
            "latency",
            "wcet",
            "migrations",
            "balance",
            "tick",
            "priority",
            "deadlines",
        ),
    ),
    ("What-if / Optimize", ("what_if", "optimize")),
)


def ai_template_by_id(tid: str) -> Optional[Tuple[str, str, str]]:
    """Return ``(id, label, prompt)`` for *tid*, or None."""
    want = (tid or "").strip()
    for item in AI_TEMPLATE_QUESTIONS:
        if item[0] == want:
            return item
    return None


# "Ask AI about this event" (timeline segment context menu) — intentionally
# kept out of AI_TEMPLATE_QUESTIONS so it does not show in the template grid.
# Keep in sync with web/src/utils/ollamaClient.js ASK_EVENT_PROMPT.
ASK_EVENT_PROMPT = (
    "Explain the timeline event for task {task} on {core} around jump:{ns} "
    "(segment {start}-{stop}). Call correlate_events and query_raw_metric as "
    "needed. Cite jump:TIME evidence."
)


def compose_ask_event_prompt(event: Optional[Dict[str, Any]]) -> str:
    """Build the ``ASK_EVENT_PROMPT`` from a timeline segment hit dict.

    *event*: ``{task, core, start, stop, ns}`` as emitted by
    ``TimelineView.ask_ai_event_requested`` / the web segment context menu.
    """
    event = event or {}

    def _num(key: str) -> str:
        v = event.get(key)
        try:
            n = float(v)
        except (TypeError, ValueError):
            return "?"
        return str(int(n)) if n.is_integer() else str(n)

    task = str(event.get("task") or "").strip() or "the selected task"
    core = str(event.get("core") or "").strip() or "its core"
    return ASK_EVENT_PROMPT.format(
        task=task, core=core, ns=_num("ns"), start=_num("start"), stop=_num("stop"),
    )

# Every provider is reached over its OpenAI-compatible /chat/completions API,
# including Ollama (http://localhost:11434/v1).
AI_PRESET_CUSTOM = "custom"
AI_PRESET_OLLAMA = "ollama"
AI_PRESET_OPENAI = "openai"
AI_PRESET_GEMINI = "gemini"

# (id, label, base_url, model)
AI_PRESETS: Tuple[Tuple[str, str, str, str], ...] = (
    (AI_PRESET_CUSTOM, "Custom", "", ""),
    (AI_PRESET_OLLAMA, "Ollama", "http://localhost:11434/v1", "qwen3.5:9b"),
    (AI_PRESET_OPENAI, "OpenAI", "https://api.openai.com/v1", "gpt-4o-mini"),
    (
        AI_PRESET_GEMINI,
        "Google Gemini",
        "https://generativelanguage.googleapis.com/v1beta/openai",
        # Rolling alias: concrete versions come and go per account/tier.
        "gemini-flash-lite-latest",
    ),
)

DEFAULT_AI_PRESET = AI_PRESET_OLLAMA
DEFAULT_AI_BASE_URL = "http://localhost:11434/v1"
DEFAULT_AI_MODEL = "qwen3.5:9b"
# Composer icons (16x16). Keep in sync with AiAssistantPanel.vue.
AI_SEND_ICON_PATH = "M8 2.5l4.5 5H9.25v6.5h-2.5V7.5H3.5L8 2.5z"
AI_STOP_ICON_PATH = "M5 5h6v6H5z"
# Keep in sync with web/src/utils/ollamaClient.js (ms equivalents).
AI_CHAT_TIMEOUT_S = 120.0
AI_LIST_MODELS_TIMEOUT_S = 12.0
AI_TEST_TIMEOUT_S = 120.0

# Per-preset settings stored in btf_viewer.rc / browser storage.
AI_PRESET_FIELDS: Tuple[str, ...] = (
    "base_url", "model", "api_key", "auth_mode", "tls_verify",
)

AI_AUTH_NONE = "none"
AI_AUTH_API_KEY = "api_key"
AI_AUTH_BROWSER = "browser"
AI_AUTH_MODES: Tuple[str, ...] = (AI_AUTH_NONE, AI_AUTH_API_KEY, AI_AUTH_BROWSER)
AI_AUTH_MODE_LABELS: Tuple[Tuple[str, str], ...] = (
    (AI_AUTH_NONE, "None (local)"),
    (AI_AUTH_API_KEY, "API key"),
    (AI_AUTH_BROWSER, "Sign in"),
)

# Hosts that serve a local model and therefore need no API key.
# Keep in sync with LOCAL_AI_HOSTS in web/src/utils/ollamaClient.js.
LOCAL_AI_HOSTS: Tuple[str, ...] = (
    "localhost",
    "127.0.0.1",
    "0.0.0.0",
    "::1",
    "host.docker.internal",
)

# Where each vendor issues API keys (shown as a Settings hint).
AI_PRESET_KEY_URLS: Dict[str, str] = {
    AI_PRESET_OPENAI: "https://platform.openai.com/api-keys",
    AI_PRESET_GEMINI: "https://aistudio.google.com/apikey",
    AI_PRESET_OLLAMA: "https://ollama.com/settings/keys",
}

AI_PRESET_SIGNIN_LABELS: Dict[str, str] = {
    AI_PRESET_OPENAI: "Sign in with OpenAI…",
    AI_PRESET_GEMINI: "Sign in with Google…",
    AI_PRESET_OLLAMA: "Open Ollama sign-in…",
    AI_PRESET_CUSTOM: "Open provider sign-in…",
}

BUILTIN_AI_PRESET_IDS = frozenset(row[0] for row in AI_PRESETS)
_AI_PRESET_ID_RE = re.compile(r"^[a-z][a-z0-9_]{0,31}$")
# Display names for extra presets added by Import… (id → combo label).
AI_EXTRA_PRESET_LABELS: Dict[str, str] = {
    "deepseek": "DeepSeek",
    "grok": "Grok",
    "xai": "xAI",
    "claude": "Claude",
    "anthropic": "Anthropic",
    "mistral": "Mistral",
    "openrouter": "OpenRouter",
}

# Synonyms of the built-in presets. Unknown vendor ids (deepseek, grok, …)
# stay as extra presets instead of collapsing onto Custom.
AI_IMPORT_PRESET_ALIASES: Dict[str, str] = {
    "chatgpt": AI_PRESET_OPENAI,
    "open_ai": AI_PRESET_OPENAI,
    "openai_compatible": AI_PRESET_CUSTOM,
    "google": AI_PRESET_GEMINI,
    "google_gemini": AI_PRESET_GEMINI,
    "gemini_openai": AI_PRESET_GEMINI,
    "ollama_cloud": AI_PRESET_OLLAMA,
    "local": AI_PRESET_OLLAMA,
}


def sanitize_ai_preset_id(raw: Optional[str]) -> str:
    """Lowercase letter-led id, or empty when the name cannot be a preset."""
    want = (raw or "").strip().lower().replace("-", "_").replace(" ", "_")
    want = re.sub(r"[^a-z0-9_]", "", want)
    want = re.sub(r"_+", "_", want).strip("_")
    if not _AI_PRESET_ID_RE.match(want):
        return ""
    return want


def ai_preset_display_label(preset_id: str, explicit: str = "") -> str:
    """Combo label for a builtin or extra preset."""
    text = (explicit or "").strip()
    if text:
        return text
    pid = sanitize_ai_preset_id(preset_id)
    for row in AI_PRESETS:
        if row[0] == pid:
            return row[1]
    if pid in AI_EXTRA_PRESET_LABELS:
        return AI_EXTRA_PRESET_LABELS[pid]
    return pid.replace("_", " ").title() if pid else "Custom"


def normalize_ai_preset(preset_id: Optional[str]) -> str:
    """Map a stored/legacy preset id onto a builtin or extra preset.

    Well-formed unknown ids (``deepseek``, ``grok``, …) are kept so Import…
    can add them to the preset list. Synonyms of the builtins still fold
    (``chatgpt`` → OpenAI). Empty / garbage ids fall back to the default.
    """
    want = sanitize_ai_preset_id(preset_id or "")
    if not want:
        return DEFAULT_AI_PRESET
    if want in BUILTIN_AI_PRESET_IDS:
        return want
    if want in AI_IMPORT_PRESET_ALIASES:
        return AI_IMPORT_PRESET_ALIASES[want]
    return want


def ai_preset_info(preset_id: str) -> Tuple[str, str, str, str]:
    """Return (id, label, base_url, model) for *preset_id*."""
    want = normalize_ai_preset(preset_id)
    for row in AI_PRESETS:
        if row[0] == want:
            return row
    return (want, ai_preset_display_label(want), "", "")


def apply_ai_preset(preset_id: str) -> Dict[str, str]:
    """Base URL / model to fill in when the user picks a preset."""
    _id, _label, base, model = ai_preset_info(preset_id)
    return {"preset": _id, "base_url": base, "model": model}


def ai_preset_setting_key(preset_id: str, field: str) -> str:
    """Settings key holding *field* for *preset_id* (e.g. ``ollama_base_url``)."""
    return f"{normalize_ai_preset(preset_id)}_{field}"


def parse_extra_ai_presets(raw: Any) -> List[Dict[str, str]]:
    """``[{id, label}, …]`` from settings JSON / the ``extra_presets`` rc key."""
    if not raw:
        return []
    data = raw
    if isinstance(data, str):
        text = data.strip()
        if not text:
            return []
        try:
            data = json.loads(text)
        except ValueError:
            return []
    if isinstance(data, dict):
        data = [
            {"id": key, **(val if isinstance(val, dict) else {"label": str(val)})}
            for key, val in data.items()
        ]
    if not isinstance(data, list):
        return []
    out: List[Dict[str, str]] = []
    seen: set[str] = set()
    for item in data:
        if isinstance(item, str):
            pid = sanitize_ai_preset_id(item)
            label = ""
        elif isinstance(item, dict):
            pid = sanitize_ai_preset_id(
                str(item.get("id") or item.get("preset") or ""))
            label = _ai_json_str(item, "label", "name")
        else:
            continue
        if not pid or pid in BUILTIN_AI_PRESET_IDS or pid in seen:
            continue
        seen.add(pid)
        out.append({"id": pid, "label": ai_preset_display_label(pid, label)})
    return out


def dump_extra_ai_presets(rows: Any) -> str:
    """Serialize extra presets for ``btf_viewer.rc`` / a settings patch."""
    parsed = parse_extra_ai_presets(rows)
    return json.dumps(parsed, ensure_ascii=False)


def extra_ai_preset_ids_from_settings(cfg: Optional[Dict[str, Any]] = None) -> List[str]:
    """Extra preset ids from ``extra_presets`` plus ``{id}_{field}`` keys."""
    c = dict(cfg or {})
    ids: List[str] = []
    seen: set[str] = set()
    for row in parse_extra_ai_presets(c.get("extra_presets")):
        pid = row["id"]
        if pid not in seen:
            ids.append(pid)
            seen.add(pid)
    suffixes = tuple("_" + field for field in AI_PRESET_FIELDS)
    for key in c:
        text = str(key or "")
        for suf in suffixes:
            if not text.endswith(suf):
                continue
            pid = sanitize_ai_preset_id(text[: -len(suf)])
            if pid and pid not in BUILTIN_AI_PRESET_IDS and pid not in seen:
                ids.append(pid)
                seen.add(pid)
            break
    return ids


def merge_ai_preset_catalog(
    extra_presets: Any = None,
    preset_settings: Optional[Dict[str, Any]] = None,
) -> List[Tuple[str, str, str, str]]:
    """Built-in presets followed by extra ones from import / saved settings."""
    rows: List[Tuple[str, str, str, str]] = list(AI_PRESETS)
    seen = set(BUILTIN_AI_PRESET_IDS)
    stored = dict(preset_settings or {})
    extras = list(parse_extra_ai_presets(extra_presets))
    for pid in stored:
        sid = sanitize_ai_preset_id(str(pid))
        if sid and sid not in seen and sid not in BUILTIN_AI_PRESET_IDS:
            if not any(e["id"] == sid for e in extras):
                extras.append({"id": sid, "label": ai_preset_display_label(sid)})
    for extra in extras:
        pid = extra["id"]
        if pid in seen:
            continue
        vals = stored.get(pid) or {}
        base = str(vals.get("base_url") or vals.get("baseUrl") or "")
        model = str(vals.get("model") or "")
        rows.append((pid, extra["label"], base, model))
        seen.add(pid)
    return rows


def resolve_ai_settings(
    cfg: Optional[Dict[str, Any]] = None,
    preset_id: Optional[str] = None,
) -> Dict[str, str]:
    """Active preset plus its stored base URL / model / API key.

    Values fall back to the preset defaults, so a never-edited preset still
    works. Pass *preset_id* to read a preset other than the selected one.
    """
    c = dict(cfg or {})
    preset = normalize_ai_preset(
        preset_id if preset_id is not None else c.get("preset"))
    _id, _label, def_base, def_model = ai_preset_info(preset)
    base_url = str(c.get(f"{preset}_base_url", "") or def_base)
    return {
        "preset": preset,
        "base_url": base_url,
        "model": str(c.get(f"{preset}_model", "") or def_model),
        "api_key": str(c.get(f"{preset}_api_key", "") or ""),
        "auth_mode": normalize_ai_auth_mode(
            c.get(f"{preset}_auth_mode", ""),
            preset_id=preset,
            base_url=base_url,
        ),
        "tls_verify": format_ai_tls_verify(c.get(f"{preset}_tls_verify", "")),
    }


def migrate_ai_settings(cfg: Optional[Dict[str, Any]] = None) -> Dict[str, str]:
    """Patch moving pre-preset settings onto the per-preset keys.

    Older builds stored one provider (``provider``) with separate ``ollama_*``
    and ``openai_*`` fields, where ``openai_*`` meant "the one OpenAI-compatible
    endpoint" and could point at any vendor. Those key names now belong to the
    OpenAI preset, so they are only read as legacy when a retired key
    (``provider``, ``openai_preset`` or ``ollama_url``) is still present, and
    they are cleared when their values belong to another preset.

    Returns only the keys that need writing; an empty dict means the settings
    are already in the current shape.
    """
    c = dict(cfg or {})
    patch: Dict[str, str] = {}
    provider = str(c.get("provider", "") or "").strip().lower().replace("-", "_")
    legacy_preset = str(c.get("openai_preset", "") or "").strip().lower()
    old_ollama_url = str(c.get("ollama_url", "") or "").strip()
    if not (provider or legacy_preset or old_ollama_url):
        return patch

    old_openai_url = str(c.get("openai_base_url", "") or "").strip()
    openai_target = _legacy_openai_target(legacy_preset, old_openai_url)

    def _keep(key: str, value: str) -> None:
        if value and not str(c.get(key, "") or "").strip():
            patch[key] = value

    if old_ollama_url:
        _keep("ollama_base_url", normalize_ai_base_url(old_ollama_url))
    _keep("ollama_model", str(c.get("ollama_model", "") or "").strip())
    _keep("ollama_api_key", str(c.get("ollama_api_key", "") or "").strip())

    old_openai_model = str(c.get("openai_model", "") or "").strip()
    old_openai_key = str(c.get("openai_api_key", "") or "").strip()
    if openai_target == AI_PRESET_OPENAI:
        # Same key names before and after; the stored values already fit.
        if old_openai_url:
            patch["openai_base_url"] = normalize_ai_base_url(old_openai_url)
    else:
        if old_openai_url:
            _keep(f"{openai_target}_base_url", normalize_ai_base_url(old_openai_url))
            patch["openai_base_url"] = ""
        _keep(f"{openai_target}_model", old_openai_model)
        _keep(f"{openai_target}_api_key", old_openai_key)
        if old_openai_model:
            patch["openai_model"] = ""
        if old_openai_key:
            patch["openai_api_key"] = ""

    if not str(c.get("preset", "") or "").strip():
        if provider and provider != "ollama":
            patch["preset"] = openai_target
        elif provider or old_ollama_url:
            patch["preset"] = AI_PRESET_OLLAMA
    return patch


def _legacy_openai_target(legacy_preset: str, legacy_base_url: str) -> str:
    """Preset that owns the retired ``openai_*`` fields."""
    want = legacy_preset.strip().lower().replace("-", "_")
    if want in ("gemini", "google", "google_gemini"):
        return AI_PRESET_GEMINI
    if want in ("openai", "chatgpt"):
        return AI_PRESET_OPENAI
    if want:
        return AI_PRESET_CUSTOM
    host = normalize_ai_base_url(legacy_base_url).lower()
    if "api.openai.com" in host:
        return AI_PRESET_OPENAI
    if "generativelanguage" in host:
        return AI_PRESET_GEMINI
    return AI_PRESET_CUSTOM


def _ai_json_tls_verify(fields: Dict[str, Any]) -> Optional[str]:
    """Return ``true``/``false`` when the import file mentions TLS verify."""
    for name in ("tls_verify", "tlsVerify", "verify_tls", "verifyTls"):
        if name in fields:
            return format_ai_tls_verify(fields.get(name), default=True)
    for name in (
        "insecure_tls", "insecureTls", "tls_insecure", "allow_insecure_tls",
        "allowInsecureTls",
    ):
        if name in fields:
            insecure = parse_ai_tls_verify(fields.get(name), default=False)
            return "false" if insecure else "true"
    return None


def _ai_json_str(obj: Dict[str, Any], *names: str) -> str:
    for name in names:
        value = obj.get(name)
        if value is not None and not isinstance(value, (dict, list)):
            text = str(value).strip()
            if text:
                return text
    return ""


def _ai_json_bool(obj: Dict[str, Any], *names: str) -> Optional[bool]:
    """Return a bool when *obj* names one of the checkbox keys."""
    for name in names:
        if name not in obj:
            continue
        value = obj.get(name)
        if value is None:
            continue
        if isinstance(value, bool):
            return value
        return parse_ai_auto_apply(value)
    return None


def _ai_import_preset_id(raw: str) -> str:
    """Preset id for an import file; unknown names become extra presets."""
    want = sanitize_ai_preset_id(raw)
    if not want:
        raise ValueError(
            f"Unknown preset {raw!r}. Use a letter-led id such as ollama "
            "or deepseek."
        )
    for row in AI_PRESETS:
        if want in (row[0], sanitize_ai_preset_id(row[1])):
            return row[0]
    if want in AI_IMPORT_PRESET_ALIASES:
        return AI_IMPORT_PRESET_ALIASES[want]
    return want


def _ai_import_preset_from_url(base_url: str) -> str:
    """Guess the preset when the file only carries a base URL."""
    host = normalize_ai_base_url(base_url).lower()
    if is_local_ai_host(host):
        return AI_PRESET_OLLAMA
    if "generativelanguage" in host or "gemini" in host:
        return AI_PRESET_GEMINI
    if "api.openai.com" in host:
        return AI_PRESET_OPENAI
    return AI_PRESET_CUSTOM


def strip_ai_settings_jsonc(text: str) -> str:
    """Drop whole-line ``//`` comments so example files can document ``auth_mode``.

    Only full-line comments are removed, so ``https://`` inside strings is safe.
    """
    lines = []
    for line in str(text or "").splitlines():
        if line.lstrip().startswith("//"):
            continue
        lines.append(line)
    return "\n".join(lines)


def parse_ai_settings_json(data: Any) -> Dict[str, str]:
    """Settings patch from an AI settings JSON file (see ``examples/ai``).

    Accepts a flat file describing one endpoint::

        {"preset": "gemini", "base_url": "…", "model": "…", "api_key": "",
         "auth_mode": "api_key"}

    or a ``presets`` object carrying several at once. Unknown preset names
    (``deepseek``, ``grok``, …) become extra presets added to the combo.
    Checkbox flags (``enabled``, ``auto_apply``, ``redact_task_names``,
    ``trace_sensitive``, ``mcp_log``) are imported when present. snake_case
    and camelCase key names both work, so files exported from either app
    import into both. Whole-line ``//`` comments are ignored. Raises
    ``ValueError`` with a user-facing message when the file cannot be applied.
    """
    if isinstance(data, (bytes, bytearray)):
        data = data.decode("utf-8", errors="replace")
    if isinstance(data, str):
        try:
            data = json.loads(strip_ai_settings_jsonc(data))
        except ValueError as exc:
            raise ValueError(f"Not valid JSON: {exc}") from exc
    if not isinstance(data, dict):
        raise ValueError("AI settings file must contain a JSON object.")

    raw_preset = _ai_json_str(data, "preset", "aiPreset", "ai_preset", "provider")
    preset = _ai_import_preset_id(raw_preset) if raw_preset else ""

    per_preset: Dict[str, Dict[str, str]] = {}
    extra_labels: Dict[str, str] = {}

    def _note_extra(target: str, fields: Optional[Dict[str, Any]] = None) -> None:
        if target in BUILTIN_AI_PRESET_IDS:
            return
        label = _ai_json_str(fields or {}, "label", "name")
        extra_labels[target] = ai_preset_display_label(
            target, label or extra_labels.get(target, ""))

    def _collect(target: str, fields: Dict[str, Any]) -> None:
        _note_extra(target, fields)
        base_url = _ai_json_str(fields, "base_url", "baseUrl", "url")
        if base_url:
            if not base_url.lower().startswith(("http://", "https://")):
                raise ValueError(
                    f"Base URL must start with http:// or https:// (got {base_url!r})."
                )
            base_url = normalize_ai_base_url(base_url)
        entry = {
            "base_url": base_url,
            "model": _ai_json_str(fields, "model", "model_id", "modelId"),
            "api_key": normalize_api_key(
                _ai_json_str(fields, "api_key", "apiKey", "key")),
        }
        auth_raw = _ai_json_str(
            fields, "auth_mode", "authMode", "authentication")
        if auth_raw:
            entry["auth_mode"] = normalize_ai_auth_mode(
                auth_raw, preset_id=target, base_url=base_url)
        tls_s = _ai_json_tls_verify(fields)
        if tls_s is not None:
            entry["tls_verify"] = tls_s
        entry = {k: v for k, v in entry.items() if v or k == "tls_verify"}
        if entry:
            per_preset.setdefault(target, {}).update(entry)

    presets_obj = data.get("presets", data.get("aiPresets"))
    if presets_obj is not None:
        if not isinstance(presets_obj, dict):
            raise ValueError('"presets" must be an object keyed by preset id.')
        for key, fields in presets_obj.items():
            if not isinstance(fields, dict):
                raise ValueError(f'Preset {key!r} must be an object.')
            _collect(_ai_import_preset_id(str(key)), fields)

    if preset:
        _note_extra(preset, data)
    flat_target = preset or _ai_import_preset_from_url(
        _ai_json_str(data, "base_url", "baseUrl", "url"))
    _collect(flat_target, data)
    if not preset and _ai_json_str(data, "base_url", "baseUrl", "url"):
        preset = flat_target
    if not preset and len(per_preset) == 1:
        preset = next(iter(per_preset))
    if not per_preset:
        raise ValueError(
            "No AI settings found. Expected base_url / model / api_key "
            "(optionally inside a presets object)."
        )

    _id, _label, def_base, _def_model = ai_preset_info(preset or DEFAULT_AI_PRESET)
    if preset and not def_base and not per_preset.get(preset, {}).get("base_url"):
        raise ValueError(f"Preset {preset!r} needs a base_url.")

    patch: Dict[str, str] = {}
    if preset:
        patch["preset"] = preset
    for target, fields in per_preset.items():
        for field, value in fields.items():
            patch[f"{target}_{field}"] = value
    extras = [
        {"id": pid, "label": extra_labels[pid]}
        for pid in extra_labels
        if pid not in BUILTIN_AI_PRESET_IDS
    ]
    extras.extend(
        row for row in parse_extra_ai_presets(
            data.get("extra_presets", data.get("extraPresets")))
        if row["id"] not in extra_labels
    )
    if extras:
        patch["extra_presets"] = dump_extra_ai_presets(extras)
    language = _ai_json_str(
        data, "response_language", "responseLanguage", "aiResponseLanguage")
    if language:
        patch["response_language"] = language
    flags = (
        ("enabled", ("enabled", "ai_enabled", "aiEnabled")),
        ("auto_apply", ("auto_apply", "ai_auto_apply", "aiAutoApply")),
        (
            "redact_task_names",
            (
                "redact_task_names", "anonymize_task_names",
                "ai_redact_task_names", "aiRedactTaskNames",
                "anonymize", "redact",
            ),
        ),
        (
            "trace_sensitive",
            (
                "trace_sensitive", "ai_trace_sensitive", "aiTraceSensitive",
                "sensitive",
            ),
        ),
        ("mcp_log", ("mcp_log", "ai_mcp_log", "aiMcpLog")),
    )
    for dest, names in flags:
        value = _ai_json_bool(data, *names)
        if value is not None:
            patch[dest] = "true" if value else "false"
    return patch


def normalize_api_key(api_key: Optional[str] = None) -> str:
    """Strip paste noise from an API key (quotes, Bearer prefix, non-ASCII junk).

    Browser ``fetch()`` rejects header values with non-ISO-8859-1 code points, so
    keep only printable ASCII (API keys are ASCII).
    """
    key = (api_key or "").strip()
    if not key:
        return ""
    # Zero-width / BOM / NBSP from rich-text paste.
    for ch in ("\ufeff", "\u200b", "\u200c", "\u200d", "\u00a0"):
        key = key.replace(ch, "")
    key = key.strip().strip("\"'").strip()
    # Unicode smart quotes / CJK punctuation often sneak in from paste.
    key = "".join(ch for ch in key if 0x20 <= ord(ch) <= 0x7E)
    key = key.strip().strip("\"'").strip()
    low = key.lower()
    if low.startswith("bearer "):
        key = key[7:].strip().strip("\"'").strip()
    # Common placeholders left in the field by mistake.
    if key.lower() in (
        "gemini_api_key",
        "your-api-key",
        "your_api_key",
        "api_key",
        "openai_api_key",
        "<api-key>",
        "xxx",
    ):
        return ""
    return key


def normalize_ai_base_url(url: str) -> str:
    """Normalize an OpenAI-compatible API root (…/v1 or vendor equivalent)."""
    u = (url or DEFAULT_AI_BASE_URL).strip().rstrip("/")
    if not u:
        return DEFAULT_AI_BASE_URL
    low = u.lower()
    # Allow pasting the full chat completions URL.
    for suffix in ("/chat/completions", "/completions"):
        if low.endswith(suffix):
            u = u[: -len(suffix)].rstrip("/")
            low = u.lower()
            break
    # Ollama's native root (…/api) is not the OpenAI-compatible one.
    if low.endswith("/api"):
        u = u[:-4].rstrip("/")
        low = u.lower()
    # A bare host (no path) means the vendor's /v1 root.
    host_only = low.split("://", 1)[-1]
    if "/" not in host_only:
        u = u + "/v1"
    return u


# Same names as the web viewer.
AI_API_KEY_ENV_NAMES = ("OPENAI_API_KEY", "GEMINI_API_KEY", "OLLAMA_API_KEY")
AI_API_KEY_REQUIRED = (
    "API key required for remote endpoints "
    "(Settings → AI → API key, or OPENAI_API_KEY / GEMINI_API_KEY / OLLAMA_API_KEY). "
    "Paste the raw key only — no Bearer prefix."
)


def read_ai_env_key(names: Optional[Any] = None) -> str:
    """First non-empty env value among *names*."""
    seq = AI_API_KEY_ENV_NAMES if names is None else names
    if isinstance(seq, str):
        seq = (seq,)
    for name in seq:
        n = str(name or "").strip()
        if not n:
            continue
        key = normalize_api_key(os.environ.get(n, ""))
        if key:
            return key
    return ""


def resolve_ai_api_key(api_key: Optional[str] = None) -> str:
    """Settings *api_key*, else OPENAI / GEMINI / OLLAMA_API_KEY."""
    key = normalize_api_key(api_key)
    if key:
        return key
    return read_ai_env_key()


def ai_request_headers(
    api_key: Optional[str] = None,
    *,
    base_url: str = "",
) -> Dict[str, str]:
    """JSON headers plus a Bearer token when a key is configured.

    Gemini OpenAI-compat (``…/v1beta/openai``) must use **only**
    ``Authorization: Bearer`` — also sending ``x-goog-api-key`` causes HTTP 400
    ("Please pass a valid API key" / "Multiple authentication credentials").
    Local Ollama needs no key at all.
    """
    headers = {"Content-Type": "application/json"}
    key = resolve_ai_api_key(api_key)
    if key:
        headers["Authorization"] = f"Bearer {key}"
    return headers


def is_local_ai_host(url: str) -> bool:
    """True for loopback endpoints (Ollama and other local servers need no key)."""
    u = normalize_ai_base_url(url)
    if "://" not in u:
        u = f"http://{u}"
    try:
        # ``hostname`` unwraps [::1] and drops the port; splitting on ':' does not.
        host = urllib.parse.urlsplit(u).hostname or ""
    except ValueError:
        return False
    return host.lower() in LOCAL_AI_HOSTS


def default_ai_auth_mode(preset_id: str = "", base_url: str = "") -> str:
    """Auth method to offer when the user has not chosen one yet."""
    pid = normalize_ai_preset(preset_id) if preset_id else ""
    if pid == AI_PRESET_OLLAMA:
        return AI_AUTH_NONE
    if base_url and is_local_ai_host(base_url):
        return AI_AUTH_NONE
    return AI_AUTH_API_KEY


def normalize_ai_auth_mode(
    value: Any,
    *,
    preset_id: str = "",
    base_url: str = "",
) -> str:
    """Map stored / imported auth method names onto ``none`` / ``api_key`` / ``browser``."""
    want = str(value or "").strip().lower().replace("-", "_").replace(" ", "_")
    aliases = {
        "none": AI_AUTH_NONE,
        "local": AI_AUTH_NONE,
        "no": AI_AUTH_NONE,
        "off": AI_AUTH_NONE,
        "api_key": AI_AUTH_API_KEY,
        "apikey": AI_AUTH_API_KEY,
        "api": AI_AUTH_API_KEY,
        "key": AI_AUTH_API_KEY,
        "token": AI_AUTH_API_KEY,
        "browser": AI_AUTH_BROWSER,
        "sign_in": AI_AUTH_BROWSER,
        "signin": AI_AUTH_BROWSER,
        "login": AI_AUTH_BROWSER,
        "oauth": AI_AUTH_BROWSER,
    }
    if want in aliases:
        return aliases[want]
    return default_ai_auth_mode(preset_id, base_url)


def parse_ai_tls_verify(value: Any, *, default: bool = True) -> bool:
    """Whether to verify the HTTPS certificate (default on)."""
    if value is None or value == "":
        return bool(default)
    if isinstance(value, bool):
        return value
    s = str(value).strip().lower()
    if s in ("0", "false", "no", "off", "disable", "disabled", "insecure"):
        return False
    if s in ("1", "true", "yes", "on", "enable", "enabled", "secure"):
        return True
    return bool(default)


def format_ai_tls_verify(value: Any, *, default: bool = True) -> str:
    return "true" if parse_ai_tls_verify(value, default=default) else "false"


def ai_ssl_context(tls_verify: bool = True):
    """``None`` uses urllib defaults; otherwise an unverified context."""
    if parse_ai_tls_verify(tls_verify, default=True):
        return None
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    return ctx


def ai_urlopen(req, timeout_s: float, *, tls_verify: bool = True):
    """``urlopen`` with optional self-signed TLS for private AI gateways."""
    kwargs: Dict[str, Any] = {"timeout": timeout_s}
    ctx = ai_ssl_context(tls_verify)
    if ctx is not None:
        kwargs["context"] = ctx
    return urllib.request.urlopen(req, **kwargs)


def _ai_ssl_error_tip(exc: BaseException, *, tls_verify: bool = True) -> str:
    msg = str(exc).lower()
    if "certificate" not in msg and "ssl" not in msg:
        return ""
    if parse_ai_tls_verify(tls_verify, default=True):
        return (
            " The endpoint presents a self-signed or private CA certificate. "
            "In Settings → AI enable Allow self-signed TLS for this preset "
            "(desktop only — browsers cannot skip certificate checks; trust "
            "the cert in the OS/browser, use http:// on a private LAN, or "
            "use the Desktop app)."
        )
    return ""


def _ai_is_timeout_error(exc: BaseException) -> bool:
    if isinstance(exc, TimeoutError):
        return True
    reason = getattr(exc, "reason", None)
    if isinstance(reason, TimeoutError):
        return True
    blob = f"{exc} {reason or ''}".lower()
    return "timed out" in blob or "timeout" in blob


def _ai_timeout_error_tip(exc: BaseException, *, timeout_s: float) -> str:
    if not _ai_is_timeout_error(exc):
        return ""
    secs = max(1, int(round(float(timeout_s) or 0)))
    return (
        f" Waited {secs}s for a non-streaming POST /chat/completions "
        "(GET /models only lists ids and does not run the model). "
        "First load of a large model is often slower — wait until it is warm "
        "and retry, or Ask in the AI tab. Confirm with curl to the same URL "
        "and body; if curl also hangs, the gateway's chat upstream is stuck. "
        "Try curl with \"stream\": true if non-stream never returns."
    )


def ai_preset_signin_url(preset_id: str, base_url: str = "") -> str:
    """Browser page to open for Sign in / Get key (Phase 1: vendor key portal)."""
    pid = normalize_ai_preset(preset_id)
    url = AI_PRESET_KEY_URLS.get(pid, "")
    if url:
        return url
    raw = str(base_url or "").strip()
    if raw.lower().startswith(("http://", "https://")):
        try:
            parts = urllib.parse.urlsplit(raw)
            if parts.scheme and parts.netloc:
                return f"{parts.scheme}://{parts.netloc}"
        except ValueError:
            pass
    return ""


def ai_preset_signin_label(preset_id: str) -> str:
    pid = normalize_ai_preset(preset_id)
    return AI_PRESET_SIGNIN_LABELS.get(pid, "Sign in…")


def ai_auth_status(
    *,
    auth_mode: str = "",
    api_key: str = "",
    base_url: str = "",
    preset_id: str = "",
) -> Dict[str, Any]:
    """Chip / CTA state for the active preset."""
    mode = normalize_ai_auth_mode(
        auth_mode, preset_id=preset_id, base_url=base_url)
    has_key = bool(resolve_ai_api_key(api_key))
    if mode == AI_AUTH_NONE:
        return {
            "mode": mode,
            "label": "Local",
            "needs_auth": False,
            "signed_in": False,
        }
    if has_key:
        if mode == AI_AUTH_BROWSER:
            return {
                "mode": mode,
                "label": "Signed in",
                "needs_auth": False,
                "signed_in": True,
            }
        return {
            "mode": mode,
            "label": "Key saved",
            "needs_auth": False,
            "signed_in": False,
        }
    return {
        "mode": mode,
        "label": "Needs sign-in" if mode == AI_AUTH_BROWSER else "Needs API key",
        "needs_auth": True,
        "signed_in": False,
    }


def format_jump_time_token(value: Any) -> str:
    """Format a trace timestamp for ``jump:TIME`` tokens."""
    try:
        v = float(value)
    except (TypeError, ValueError):
        return str(value)
    if v.is_integer():
        return str(int(v))
    return f"{v:g}"


def placed_cursor_times(cursors: Optional[Sequence[Any]] = None) -> List[float]:
    """Sorted numeric cursor times (skip nulls)."""
    out: List[float] = []
    for c in cursors or []:
        if c is None or c == "":
            continue
        try:
            out.append(float(c))
        except (TypeError, ValueError):
            continue
    out.sort()
    return out


def cursor_region_bounds(
    cursors: Optional[Sequence[Any]] = None,
) -> Optional[Tuple[float, float]]:
    """``(lo, hi)`` from earliest/latest placed cursor, or None if <2."""
    placed = placed_cursor_times(cursors)
    if len(placed) < 2:
        return None
    lo, hi = placed[0], placed[-1]
    if hi <= lo:
        return None
    return lo, hi


def append_explain_region_bounds(
    prompt: str,
    cursors: Optional[Sequence[Any]] = None,
) -> str:
    """Append an explicit C1–Cn jump window to the Explain-region prompt."""
    bounds = cursor_region_bounds(cursors)
    if not bounds:
        return str(prompt or "")
    lo, hi = bounds
    lo_s, hi_s = format_jump_time_token(lo), format_jump_time_token(hi)
    extra = (
        f"Cursor region window: jump:{lo_s} … jump:{hi_s}. "
        "ONLY cite jump:TIME evidence inside this window. "
        "If tools return no in-window events, say the region has no matching "
        "evidence — do not invent timestamps or task names."
    )
    base = str(prompt or "").rstrip()
    return f"{base}\n\n{extra}" if base else extra


def normalize_ai_context(ctx: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Accept snake_case or camelCase context keys (Desktop / Web parity)."""
    c = dict(ctx or {})
    findings = c.get("findings_text")
    if findings is None or findings == "":
        findings = c.get("findingsText", "")
    cursors = c.get("cursors")
    if cursors is None:
        cursors = []
    elif not isinstance(cursors, (list, tuple)):
        cursors = [cursors]
    return {
        "findings_text": findings or "",
        "span": c.get("span", "") or "",
        "cores": c.get("cores", ""),
        "scope": c.get("scope", "") or "",
        "metrics": c.get("metrics"),
        "cursors": list(cursors),
        "findings": list(c.get("findings") or []),
    }


_JUMP_RE = re.compile(r"jump:([0-9]+(?:\.[0-9]+)?)")
_RANGE_RE = re.compile(r"range:([0-9]+(?:\.[0-9]+)?)/([0-9]+(?:\.[0-9]+)?)")
_MD_INLINE_CODE_RE = re.compile(r"`([^`\n]+)`")
_MD_BOLD_RE = re.compile(r"(\*\*|__)(.+?)\1")
_MD_ITALIC_RE = re.compile(r"(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)|(?<!_)_(?!_)(.+?)(?<!_)_(?!_)")
_MD_LINK_RE = re.compile(r"\[([^\]]+)\]\(([^)]+)\)")


def extract_jump_times(text: str) -> List[float]:
    """Parse ``jump:NNNN`` tokens from assistant text (parity with web)."""
    out: List[float] = []
    for m in _JUMP_RE.finditer(text or ""):
        try:
            out.append(float(m.group(1)))
        except ValueError:
            continue
    return out


def ai_jump_annotation_note(value: float) -> str:
    """Annotation label for a clicked ``jump:TIME`` link (web parity)."""
    try:
        v = float(value)
    except (TypeError, ValueError):
        return "AI jump"
    if v.is_integer():
        return f"AI jump:{int(v)}"
    return f"AI jump:{value}"


def _md_inline_to_html_escaped(text: str) -> str:
    """Escape text and apply inline markdown (code, bold, italic, links, jump:N)."""
    placeholders: List[str] = []

    def _stash(frag: str) -> str:
        placeholders.append(frag)
        return f"\x00MD{len(placeholders) - 1}\x00"

    parts: List[Tuple[str, str]] = []
    last = 0
    src = text or ""
    for m in _MD_INLINE_CODE_RE.finditer(src):
        parts.append(("t", src[last:m.start()]))
        parts.append(("c", m.group(1)))
        last = m.end()
    parts.append(("t", src[last:]))

    out_chunks: List[str] = []
    for kind, val in parts:
        if kind == "c":
            # Models often wrap jump:TIME in backticks; keep those clickable.
            rm = _RANGE_RE.fullmatch(val.strip())
            if rm:
                out_chunks.append(_stash(
                    f'<a href="{btf_range_href(rm.group(1), rm.group(2))}" '
                    f'class="ai-jump">range:{rm.group(1)}/{rm.group(2)}</a>'
                ))
                continue
            jm = _JUMP_RE.fullmatch(val.strip())
            if jm:
                out_chunks.append(_stash(
                    f'<a href="{btf_jump_href(jm.group(1))}" class="ai-jump">'
                    f"jump:{jm.group(1)}</a>"
                ))
            else:
                out_chunks.append(_stash(f"<code>{html.escape(val)}</code>"))
            continue
        seg = val
        seglast = 0
        buf: List[str] = []
        for lm in _MD_LINK_RE.finditer(seg):
            buf.append(html.escape(seg[seglast:lm.start()]))
            label = html.escape(lm.group(1))
            href = lm.group(2).strip()
            low = href.lower()
            if low.startswith("btfhighlight:"):
                name = parse_btf_highlight_href(href)
                href = btf_highlight_href(name) if name else href
                low = href.lower()
            if (
                low.startswith("http://")
                or low.startswith("https://")
                or low.startswith("btfjump:")
                or low.startswith("btfrange:")
                or low.startswith("btfhighlight:")
                or low.startswith("btfhyp:")
                or low.startswith("btfscope:")
                or low.startswith("btfexp:")
                or low.startswith("btftool:")
                or low.startswith("mailto:")
            ):
                buf.append(
                    _stash(f'<a href="{html.escape(href, quote=True)}">{label}</a>')
                )
            else:
                buf.append(html.escape(lm.group(0)))
            seglast = lm.end()
        buf.append(html.escape(seg[seglast:]))
        chunk = "".join(buf)
        chunk = _MD_BOLD_RE.sub(lambda m: f"<strong>{m.group(2)}</strong>", chunk)

        def _ital(m: re.Match) -> str:
            body = m.group(1) if m.group(1) is not None else m.group(2)
            return f"<em>{body}</em>"

        chunk = _MD_ITALIC_RE.sub(_ital, chunk)
        chunk = _RANGE_RE.sub(
            lambda m: _stash(
                f'<a href="{btf_range_href(m.group(1), m.group(2))}" '
                f'class="ai-jump">range:{m.group(1)}/{m.group(2)}</a>'
            ),
            chunk,
        )
        chunk = _JUMP_RE.sub(
            lambda m: _stash(
                f'<a href="{btf_jump_href(m.group(1))}" class="ai-jump">'
                f"jump:{m.group(1)}</a>"
            ),
            chunk,
        )
        out_chunks.append(chunk)

    result = "".join(out_chunks)
    for i, frag in enumerate(placeholders):
        result = result.replace(f"\x00MD{i}\x00", frag)
    return result


_MD_TABLE_ALIGN_RE = re.compile(r"^:?-{1,}:?$")
_HTML_TABLE_START_RE = re.compile(r"^<table\b", re.IGNORECASE)
_HTML_TABLE_END_RE = re.compile(r"</table\s*>", re.IGNORECASE)
def _ai_md_th_style(is_dark: bool = True) -> str:
    if is_dark:
        return (
            "border:1px solid #3a4658;padding:4px 8px;"
            "background:#243044;color:#e8eef6;font-weight:600;"
        )
    return (
        "border:1px solid #DDDDDD;padding:4px 8px;"
        "background:#E8EEF4;color:#1E1E1E;font-weight:600;"
    )


def _ai_md_td_style(is_dark: bool = True) -> str:
    if is_dark:
        return (
            "border:1px solid #3a4658;padding:4px 8px;"
            "background:#1a2230;color:#dbe2ea;"
        )
    return (
        "border:1px solid #DDDDDD;padding:4px 8px;"
        "background:#FFFFFF;color:#1E1E1E;"
    )


_AI_MD_TH_STYLE = _ai_md_th_style(True)
_AI_MD_TD_STYLE = _ai_md_td_style(True)
_AI_MD_TABLE_OPEN = (
    '<table class="ai-md-table" width="100%" cellspacing="0" cellpadding="4">'
)


def _split_md_table_row(line: str) -> List[str]:
    s = (line or "").strip()
    if s.startswith("|"):
        s = s[1:]
    if s.endswith("|") and not s.endswith("\\|"):
        s = s[:-1]
    return [p.strip().replace("\\|", "|") for p in re.split(r"(?<!\\)\|", s)]


def _is_md_table_separator(line: str) -> bool:
    if "|" not in (line or ""):
        return False
    cells = _split_md_table_row(line)
    if not cells:
        return False
    for cell in cells:
        compact = re.sub(r"\s+", "", cell)
        if not compact or not _MD_TABLE_ALIGN_RE.fullmatch(compact):
            return False
    return True


def _md_table_aligns(sep_line: str, ncols: int) -> List[str]:
    cells = _split_md_table_row(sep_line)
    out: List[str] = []
    for i in range(ncols):
        compact = re.sub(r"\s+", "", cells[i]) if i < len(cells) else ""
        left = compact.startswith(":")
        right = compact.endswith(":")
        if left and right:
            out.append("center")
        elif right:
            out.append("right")
        else:
            out.append("left")
    return out


def _md_table_cell_html(tag: str, text: str, align: str, *, is_dark: bool = True) -> str:
    style = _ai_md_th_style(is_dark) if tag == "th" else _ai_md_td_style(is_dark)
    al = align if align in ("left", "right", "center") else "left"
    return (
        f'<{tag} align="{al}" style="{style}">'
        f"{_md_inline_to_html_escaped(text)}</{tag}>"
    )


def _md_table_html(header: List[str], aligns: List[str],
                   rows: List[List[str]], *, is_dark: bool = True) -> str:
    ncols = max(1, len(header))

    def _pad(cells: List[str]) -> List[str]:
        padded = list(cells[:ncols])
        while len(padded) < ncols:
            padded.append("")
        return padded

    header = _pad(header)
    thead = "<tr>" + "".join(
        _md_table_cell_html("th", header[i], aligns[i] if i < len(aligns) else "left",
                            is_dark=is_dark)
        for i in range(ncols)
    ) + "</tr>"
    body: List[str] = []
    for row in rows:
        cells = _pad(row)
        body.append(
            "<tr>" + "".join(
                _md_table_cell_html(
                    "td", cells[i], aligns[i] if i < len(aligns) else "left",
                    is_dark=is_dark)
                for i in range(ncols)
            ) + "</tr>"
        )
    return (
        f"{_AI_MD_TABLE_OPEN}<thead>{thead}</thead>"
        f"<tbody>{''.join(body)}</tbody></table>"
    )


class _SafeAiTableHtmlParser(HTMLParser):
    """Keep table markup only; drop scripts and event-handler attributes."""

    _KEEP = frozenset({
        "table", "thead", "tbody", "tfoot", "tr", "th", "td", "caption", "br",
    })
    _SKIP_INNER = frozenset({
        "script", "style", "iframe", "object", "embed", "link", "meta", "svg",
    })

    def __init__(self, is_dark: bool = True) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: List[str] = []
        self._skip = 0
        self.saw_table = False
        self._is_dark = bool(is_dark)

    def handle_starttag(self, tag: str, attrs) -> None:
        tag = (tag or "").lower()
        if tag in self._SKIP_INNER:
            self._skip += 1
            return
        if self._skip or tag not in self._KEEP:
            return
        if tag == "table":
            self.saw_table = True
            self.parts.append(_AI_MD_TABLE_OPEN)
            return
        if tag == "br":
            self.parts.append("<br>")
            return
        extra: List[str] = []
        align = ""
        for key, val in attrs or ():
            key = (key or "").lower()
            val = val or ""
            if key == "align" and val.lower() in ("left", "right", "center"):
                align = val.lower()
            elif key in ("colspan", "rowspan") and str(val).isdigit():
                n = int(val)
                if 1 <= n <= 32:
                    extra.append(f'{key}="{n}"')
        if tag in ("th", "td"):
            if align:
                extra.append(f'align="{align}"')
            style = _ai_md_th_style(self._is_dark) if tag == "th" else _ai_md_td_style(self._is_dark)
            extra.append(f'style="{style}"')
        attr = (" " + " ".join(extra)) if extra else ""
        self.parts.append(f"<{tag}{attr}>")

    def handle_endtag(self, tag: str) -> None:
        tag = (tag or "").lower()
        if tag in self._SKIP_INNER:
            self._skip = max(0, self._skip - 1)
            return
        if self._skip or tag not in self._KEEP or tag == "br":
            return
        self.parts.append(f"</{tag}>")

    def handle_startendtag(self, tag: str, attrs) -> None:
        if (tag or "").lower() == "br" and not self._skip:
            self.parts.append("<br>")
            return
        self.handle_starttag(tag, attrs)
        self.handle_endtag(tag)

    def handle_data(self, data: str) -> None:
        if self._skip or not data:
            return
        self.parts.append(_md_inline_to_html_escaped(data))


def _sanitize_html_table_block(block: str, *, is_dark: bool = True) -> str:
    parser = _SafeAiTableHtmlParser(is_dark=is_dark)
    try:
        parser.feed(block or "")
        parser.close()
    except Exception:
        return ""
    html_out = "".join(parser.parts).strip()
    if not parser.saw_table or "<table" not in html_out.lower():
        return ""
    return html_out


def markdown_to_safe_html(text: str, *, as_img: bool = True, is_dark: bool = True) -> str:
    """Convert a subset of Markdown to safe HTML (AI reply preview).

    ``as_img=True`` (QTextBrowser chat) embeds mermaid as a PNG-compatible
    data-URI ``<img>``. ``as_img=False`` (HTML export / browser) keeps an
    inline SVG so diagram nodes stay clickable.
    """
    raw = (text or "").replace("\r\n", "\n").replace("\r", "\n").strip()
    if not raw:
        return ""
    lines = raw.split("\n")
    out: List[str] = []
    i = 0
    n = len(lines)

    def _flush_para(buf: List[str]) -> None:
        if not buf:
            return
        body = "<br>".join(_md_inline_to_html_escaped(s.strip()) for s in buf)
        out.append(f"<p>{body}</p>")
        buf.clear()

    para: List[str] = []
    while i < n:
        line = lines[i]
        stripped = line.strip()

        if stripped.startswith("```"):
            _flush_para(para)
            lang = stripped[3:].strip()
            i += 1
            code_lines: List[str] = []
            while i < n and not lines[i].strip().startswith("```"):
                code_lines.append(lines[i])
                i += 1
            if i < n:
                i += 1
            if lang.lower() == "mermaid":
                out.append(mermaid_block_html(
                    "\n".join(code_lines), as_img=as_img, zoomable=as_img))
                continue
            code_html = html.escape("\n".join(code_lines))
            cls = f' class="language-{html.escape(lang)}"' if lang else ""
            out.append(f"<pre><code{cls}>{code_html}</code></pre>")
            continue

        if not stripped:
            _flush_para(para)
            i += 1
            continue

        if re.fullmatch(r"(-{3,}|\*{3,}|_{3,})", stripped):
            _flush_para(para)
            out.append("<hr>")
            i += 1
            continue

        hm = re.match(r"^(#{1,4})\s+(.+)$", stripped)
        if hm:
            _flush_para(para)
            level = len(hm.group(1))
            out.append(
                f"<h{level}>{_md_inline_to_html_escaped(hm.group(2).strip())}</h{level}>"
            )
            i += 1
            continue

        if stripped.startswith(">"):
            _flush_para(para)
            qlines: List[str] = []
            while i < n and lines[i].strip().startswith(">"):
                qlines.append(re.sub(r"^>\s?", "", lines[i].strip()))
                i += 1
            out.append(
                f"<blockquote>{_md_inline_to_html_escaped(' '.join(qlines))}</blockquote>"
            )
            continue

        if re.match(r"^[-*+]\s+", stripped) or re.match(r"^\d+\.\s+", stripped):
            _flush_para(para)
            ordered = bool(re.match(r"^\d+\.\s+", stripped))
            tag = "ol" if ordered else "ul"
            items: List[str] = []
            start_num = 0
            while i < n:
                s = lines[i].strip()
                if ordered:
                    # Models often interrupt 1./2./3. with paragraphs and nested
                    # bullets; each run becomes its own <ol>, so honour the
                    # source number via start=/value=.
                    m = re.match(r"^(\d+)\.\s+(.*)$", s)
                    if not m:
                        break
                    num = int(m.group(1))
                    if not start_num:
                        start_num = num
                    val = (
                        ""
                        if num == start_num + len(items)
                        else f' value="{num}"'
                    )
                    items.append(
                        f"<li{val}>{_md_inline_to_html_escaped(m.group(2))}</li>"
                    )
                else:
                    m = re.match(r"^[-*+]\s+(.*)$", s)
                    if not m:
                        break
                    items.append(
                        f"<li>{_md_inline_to_html_escaped(m.group(1))}</li>"
                    )
                i += 1
            start_attr = f' start="{start_num}"' if ordered and start_num > 1 else ""
            out.append(f"<{tag}{start_attr}>{''.join(items)}</{tag}>")
            continue

        if _HTML_TABLE_START_RE.match(stripped):
            _flush_para(para)
            buf = [stripped]
            found_end = bool(_HTML_TABLE_END_RE.search(stripped))
            i += 1
            while i < n and not found_end:
                buf.append(lines[i])
                if _HTML_TABLE_END_RE.search(lines[i]):
                    found_end = True
                i += 1
            block = "\n".join(buf)
            safe = _sanitize_html_table_block(block, is_dark=is_dark)
            if safe:
                out.append(safe)
            else:
                out.append(f"<p>{_md_inline_to_html_escaped(block)}</p>")
            continue

        if (
            "|" in stripped
            and i + 1 < n
            and _is_md_table_separator(lines[i + 1].strip())
        ):
            _flush_para(para)
            header_cells = _split_md_table_row(stripped)
            aligns = _md_table_aligns(lines[i + 1].strip(), max(1, len(header_cells)))
            i += 2
            body_rows: List[List[str]] = []
            while i < n:
                s = lines[i].strip()
                if not s or "|" not in s or s.startswith("```"):
                    break
                if re.match(r"^#{1,4}\s+", s) or _HTML_TABLE_START_RE.match(s):
                    break
                if _is_md_table_separator(s):
                    i += 1
                    continue
                body_rows.append(_split_md_table_row(s))
                i += 1
            out.append(_md_table_html(header_cells, aligns, body_rows, is_dark=is_dark))
            continue

        para.append(stripped)
        i += 1

    _flush_para(para)
    return "".join(out)


def _ai_message_body_html(role: str, text: str, *, as_img: bool = True,
                          is_dark: bool = True) -> str:
    """Message body without the role prefix; assistant replies render as Markdown."""
    body_text = (text or "").strip()
    if role in ("assistant", "evidence"):
        return markdown_to_safe_html(
            body_text, as_img=as_img, is_dark=is_dark) or "<p></p>"
    esc = html.escape(body_text)
    linked = _JUMP_RE.sub(
        lambda m: (
            f'<a href="{btf_jump_href(m.group(1))}" class="ai-jump">'
            f"jump:{m.group(1)}</a>"
        ),
        esc,
    )
    return linked.replace("\n", "<br>")


# QTextBrowser CSS is limited; keep selectors simple (no descendant chains).
def _ai_log_style(is_dark: bool = True) -> str:
    if is_dark:
        pre_bg, pre_bd, quote, hr, link = (
            "#1a2230", "#3a4658", "#a8b4c4", "#3a4658", "#5b9bd5")
        user, asst, tool = "#6ea8e0", "#6fbf9a", "#e6d48a"
    else:
        pre_bg, pre_bd, quote, hr, link = (
            "#FFFFFF", "#DDDDDD", "#555555", "#DDDDDD", "#0066CC")
        user, asst, tool = "#0066CC", "#2e7d57", "#6b5508"
    return (
        "h1,h2,h3,h4{margin:8px 0 4px;font-size:13px;}"
        "h1{font-size:15px;}h2{font-size:14px;}"
        "p{margin:4px 0;}"
        "ul,ol{margin:4px 0 4px 18px;padding:0;}"
        "li{margin:2px 0;}"
        f"pre{{background:{pre_bg};border:1px solid {pre_bd};border-radius:4px;"
        "padding:8px;margin:6px 0;white-space:pre-wrap;}"
        "code{font-family:Menlo,Consolas,Monaco,'Courier New',monospace;font-size:11px;}"
        "p code,li code{background:rgba(127,127,127,0.18);padding:1px 4px;border-radius:3px;}"
        f"blockquote{{margin:6px 0;padding:4px 10px;border-left:3px solid {link};"
        f"color:{quote};}}"
        f"hr{{border:none;border-top:1px solid {hr};margin:8px 0;}}"
        f"a{{color:{link};}}"
        "table.ai-md-table{margin:8px 0;}"
        ".ai-role{font-size:11px;font-weight:600;}"
        f".ai-role-user{{color:{user};}}"
        f".ai-role-assistant{{color:{asst};}}"
        f".ai-tool-card{{color:{tool};}}"
        "img.ai-mermaid-img{max-width:100%;height:auto;border-radius:4px;}"
        "a.ai-mermaid-zoom,.ai-mermaid-zoom{cursor:zoom-in;text-decoration:none;}"
        ".ai-evidence-score{font-family:Menlo,Consolas,Monaco,'Courier New',monospace;}"
    )


_AI_LOG_STYLE = _ai_log_style(True)


def ai_entry_role(entry: Any) -> str:
    if isinstance(entry, dict):
        return str(entry.get("role") or "assistant")
    return str(entry[0])


def ai_entry_text(entry: Any) -> str:
    if isinstance(entry, dict):
        return str(entry.get("text") or entry.get("content") or "")
    if isinstance(entry, (list, tuple)) and len(entry) > 1:
        return str(entry[1] or "")
    return ""


def ai_entry_tools(entry: Any) -> List[Dict[str, Any]]:
    if isinstance(entry, dict):
        tools = entry.get("tools") or []
        return list(tools) if isinstance(tools, list) else []
    return []


def _tool_cards_html(tools: Sequence[Dict[str, Any]], batch_id: str,
                     *, light: bool = False) -> str:
    if not tools:
        return ""
    rows: List[str] = []
    status = "pending"
    for t in tools:
        if isinstance(t, dict) and t.get("status"):
            status = str(t.get("status") or status)
            break
    st_color = "#6b7280" if light else "#8b98a8"
    for t in tools:
        if not isinstance(t, dict):
            continue
        name = str(t.get("name") or "")
        args = t.get("arguments") if isinstance(t.get("arguments"), dict) else {}
        label = html.escape(summarise_tool_call(name, args))
        st = html.escape(str(t.get("status") or status))
        rows.append(
            f"<p>⚡ {label} <span style=\"color:{st_color}\">({st})</span></p>"
        )
        detail = ""
        if str(t.get("status") or status) == "failed":
            detail = str(t.get("result") or t.get("error") or "").strip()
        if detail:
            rows.append(
                f"<p style=\"margin:2px 0 6px 1.2em;color:{st_color};"
                f"font-size:11px;\">{html.escape(detail)}</p>"
            )
    actions = ""
    if status == "pending" and batch_id:
        actions = (
            f'<p><a href="btfaction:apply/{html.escape(batch_id)}">Apply</a>'
            f' · <a href="btfaction:skip/{html.escape(batch_id)}">Skip</a></p>'
        )
    elif status == "applied" and batch_id:
        actions = (
            f'<p><a href="btfaction:undo/{html.escape(batch_id)}">Undo</a></p>'
        )
    if light:
        return (
            '<div class="ai-tool-card" style="margin-top:8px;padding:8px 10px;'
            'border-left:3px solid #c9a227;background:#fff8e8;color:#6b5508;">'
            f"{''.join(rows)}{actions}</div>"
        )
    return (
        '<table width="100%" cellspacing="0" cellpadding="0">'
        '<tr><td bgcolor="#2a2418" class="ai-tool-card" '
        'style="border-left:3px solid #c9a227;padding:8px 10px;">'
        f"{''.join(rows)}{actions}</td></tr></table>"
    )


# Visible role labels (panel + Save As). Keep in sync with aiMarkdown.js.
AI_ROLE_LABEL_USER = "Your prompt"
AI_ROLE_LABEL_ASSISTANT = "AI Assistant"
AI_ROLE_LABEL_EVIDENCE = "Evidence / Reasoning"


def ai_role_label(
    role: str,
    response_language: str = DEFAULT_AI_RESPONSE_LANGUAGE,
) -> str:
    """Human-readable speaker label for a chat turn."""
    if role == "user":
        return AI_ROLE_LABEL_USER
    if role == "evidence":
        return evidence_panel_labels(response_language)["role"]
    return AI_ROLE_LABEL_ASSISTANT


def _format_ai_log_html(
    role: str,
    text: str,
    tools: Optional[Sequence[Dict[str, Any]]] = None,
    batch_id: str = "",
    response_language: str = DEFAULT_AI_RESPONSE_LANGUAGE,
    *,
    is_dark: bool = True,
) -> str:
    """One conversation turn as a self-contained table (Qt will not merge these)."""
    is_user = role == "user"
    label = html.escape(ai_role_label(role, response_language))
    role_cls = "ai-role-user" if is_user else (
        "ai-role-evidence" if role == "evidence" else "ai-role-assistant")
    # bgcolor is more reliable in QTextBrowser than CSS background on divs.
    if is_dark:
        bg = "#1e3348" if is_user else (
            "#1f2430" if role == "evidence" else "#1a2620")
        fg = "#e8eef7" if is_user else (
            "#c5d0dc" if role == "evidence" else "#d5e4f7")
    else:
        bg = "#e8f1fa" if is_user else (
            "#eef0f3" if role == "evidence" else "#e8f6ee")
        fg = "#1E1E1E"
    bar = "#5b9bd5" if is_user else (
        "#8a96a8" if role == "evidence" else "#3d9a72")
    body = _ai_message_body_html(role, text, is_dark=is_dark) if (text or "").strip() else ""
    cards = _tool_cards_html(tools or [], batch_id, light=not is_dark)
    if not body and not cards:
        body = "<p></p>"
    return (
        f'<table class="ai-turn" width="100%" cellspacing="0" cellpadding="0">'
        f'<tr><td class="ai-role {role_cls}" style="padding:10px 0 3px 0;">{label}</td></tr>'
        f'<tr><td class="ai-bubble" bgcolor="{bg}" '
        f'style="border-left:3px solid {bar};padding:8px 10px;color:{fg};">{body}{cards}</td></tr>'
        f"</table>"
    )


def _ai_log_document_html(
    entries: Sequence[Any],
    response_language: str = DEFAULT_AI_RESPONSE_LANGUAGE,
    *,
    is_dark: bool = True,
) -> str:
    """Full conversation document for QTextBrowser.setHtml (avoids append merge)."""
    if not entries:
        return ""
    parts: List[str] = []
    for i, entry in enumerate(entries):
        if i:
            parts.append('<hr class="ai-turn-sep">')
        parts.append(_format_ai_log_html(
            ai_entry_role(entry),
            ai_entry_text(entry),
            ai_entry_tools(entry),
            str((entry.get("batch_id") if isinstance(entry, dict) else "") or ""),
            response_language=response_language,
            is_dark=is_dark,
        ))
    return f"<html><body>{''.join(parts)}</body></html>"


def _ai_file_stamp() -> str:
    return datetime.datetime.now().strftime("%Y%m%d-%H%M%S")


def _tool_transcript_lines(entry: Any) -> List[str]:
    lines: List[str] = []
    for t in ai_entry_tools(entry):
        if not isinstance(t, dict):
            continue
        name = str(t.get("name") or "")
        args = t.get("arguments") if isinstance(t.get("arguments"), dict) else {}
        st = str(t.get("status") or "pending")
        lines.append(f"- ⚡ {summarise_tool_call(name, args)} ({st})")
    return lines


def format_ai_conversation_markdown(
    entries: Sequence[Any],
    response_language: str = DEFAULT_AI_RESPONSE_LANGUAGE,
) -> str:
    """Markdown transcript of the conversation (assistant replies kept as-is)."""
    stamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    out = ["# BTF Viewer — AI Conversation", "", f"_Saved {stamp}_", ""]
    for entry in entries:
        role = ai_entry_role(entry)
        text = (ai_entry_text(entry) or "").strip()
        tools = _tool_transcript_lines(entry)
        out.append(f"## {ai_role_label(role, response_language)}")
        out.append("")
        if text:
            out.append(text)
            out.append("")
        if tools:
            out.extend(tools)
            out.append("")
    return "\n".join(out).rstrip() + "\n"


def format_ai_conversation_text(
    entries: Sequence[Any],
    response_language: str = DEFAULT_AI_RESPONSE_LANGUAGE,
) -> str:
    """Plain-text transcript of the conversation."""
    stamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    out = ["BTF Viewer — AI Conversation", f"Saved {stamp}", ""]
    for entry in entries:
        role = ai_entry_role(entry)
        text = (ai_entry_text(entry) or "").strip()
        tools = _tool_transcript_lines(entry)
        out.append(f"{ai_role_label(role, response_language)}:")
        if text:
            out.append(text)
        if tools:
            out.extend(tools)
        out.append("")
    return "\n".join(out).rstrip() + "\n"


_AI_HTML_STYLE = ""  # legacy; conversation HTML uses html_report chrome


def format_ai_conversation_html_body(
    entries: Sequence[Any],
    response_language: str = DEFAULT_AI_RESPONSE_LANGUAGE,
) -> str:
    """Conversation turn markup only (no document chrome). For report embedding."""
    parts = []
    for entry in entries:
        role = ai_entry_role(entry)
        text = ai_entry_text(entry)
        cls = "user" if role == "user" else (
            "evidence" if role == "evidence" else "assistant")
        body = _ai_message_body_html(role, text, as_img=False) if (text or "").strip() else ""
        cards = _tool_cards_html(ai_entry_tools(entry), "", light=True)
        head = f"<h3>{html.escape(ai_role_label(role, response_language))}</h3>"
        parts.append(
            f'<section class="msg {cls}">{head}'
            f'<div class="body">{body}{cards}</div>'
            "</section>"
        )
    return "\n".join(parts)


def format_ai_conversation_html(
    entries: Sequence[Any],
    response_language: str = DEFAULT_AI_RESPONSE_LANGUAGE,
) -> str:
    """Standalone HTML transcript (Markdown rendered, same styling as the panel.

    Keep in sync with aiMarkdown.js::formatAiConversationHtml; Qt's own
    ``toHtml()`` would export editor-flavoured markup instead.
    """
    stamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    turns = format_ai_conversation_html_body(entries, response_language)
    body = (
        '<section class="report-card">\n'
        "<h2>Conversation</h2>\n"
        f"{turns}\n"
        "</section>"
    )
    return btf_html_report_document(
        "AI Conversation",
        body,
        subtitle=f"Saved {stamp}",
        doc_title="BTFViewer — AI Conversation",
    )


def build_ai_user_message(
    query: str,
    *,
    findings_text: str = "",
    metrics: Optional[Dict[str, Any]] = None,
    span: str = "",
    cores: Any = "",
    scope: str = "",
    cursors: Optional[Sequence[Any]] = None,
) -> str:
    """Assemble the user turn: context + question."""
    parts = ["### System Trace Context"]
    if span:
        parts.append(f"- Trace Span: {span}")
    if cores != "" and cores is not None:
        parts.append(f"- Cores: {cores}")
    if scope:
        parts.append(f"- Statistics scope: {scope}")
    placed = placed_cursor_times(cursors)
    if placed:
        labels = ", ".join(
            f"C{i + 1}=jump:{format_jump_time_token(t)}"
            for i, t in enumerate(placed)
        )
        parts.append(f"- Timeline cursors: {labels}")
        bounds = cursor_region_bounds(placed)
        if bounds:
            lo_s = format_jump_time_token(bounds[0])
            hi_s = format_jump_time_token(bounds[1])
            parts.append(
                f"- Cursor region window: jump:{lo_s} … jump:{hi_s} "
                "(only cite jump:TIME evidence inside this window when "
                "explaining the region)"
            )
    parts.append("")
    parts.append("### Analysis Findings")
    parts.append((findings_text or "No findings for the current scope.").rstrip())
    parts.append("")
    if metrics:
        parts.append("### Extracted Relevant Metrics")
        parts.append(json.dumps(metrics, indent=2, default=str))
        parts.append("")
    parts.append("### User Question")
    parts.append(query.strip())
    return "\n".join(parts)


def _build_chat_messages(
    query: str,
    *,
    findings_text: str = "",
    metrics: Optional[Dict[str, Any]] = None,
    span: str = "",
    cores: Any = "",
    scope: str = "",
    cursors: Optional[Sequence[Any]] = None,
    response_language: str = DEFAULT_AI_RESPONSE_LANGUAGE,
    history: Optional[Sequence[Dict[str, str]]] = None,
) -> List[Dict[str, str]]:
    messages: List[Dict[str, str]] = [
        {"role": "system", "content": build_ai_system_prompt(response_language)},
    ]
    if history:
        for m in history:
            role = m.get("role")
            content = m.get("content")
            if role in ("user", "assistant") and content:
                messages.append({"role": role, "content": str(content)})
    messages.append({
        "role": "user",
        "content": build_ai_user_message(
            query,
            findings_text=findings_text,
            metrics=metrics,
            span=span,
            cores=cores,
            scope=scope,
            cursors=cursors,
        ),
    })
    return messages


def _read_http_body(
    resp: Any,
    *,
    cancel_event: Optional[threading.Event] = None,
) -> bytes:
    chunks: List[bytes] = []
    while True:
        if cancel_event is not None and cancel_event.is_set():
            raise OllamaCancelled("Stopped")
        try:
            chunk = resp.read(16384)
        except Exception as exc:
            if cancel_event is not None and cancel_event.is_set():
                raise OllamaCancelled("Stopped") from exc
            raise
        if not chunk:
            break
        chunks.append(chunk)
    return b"".join(chunks)


def summarize_ai_http_error_detail(detail: str) -> str:
    """Vendor error message from an HTTP body, without JSON/HTML dump."""
    text = str(detail or "").strip()
    if not text:
        return ""
    head = text[:64].lstrip().lower()
    if head.startswith("<!doctype") or head.startswith("<html"):
        return ""

    data: Any = None
    try:
        data = json.loads(text)
    except ValueError:
        start_obj = text.find("{")
        start_arr = text.find("[")
        starts = [i for i in (start_obj, start_arr) if i >= 0]
        if starts:
            try:
                data = json.loads(text[min(starts):])
            except ValueError:
                data = None

    def _walk(obj: Any) -> str:
        if isinstance(obj, list) and obj:
            return _walk(obj[0])
        if isinstance(obj, dict):
            err = obj.get("error")
            if isinstance(err, str) and err.strip():
                return err.strip()
            if isinstance(err, dict):
                msg = err.get("message") or err.get("msg")
                if msg:
                    return str(msg).strip()
            msg = obj.get("message") or obj.get("msg")
            if msg:
                return str(msg).strip()
        if isinstance(obj, str):
            return obj.strip()
        return ""

    msg = _walk(data) if data is not None else ""
    if not msg:
        m = re.search(r'"message"\s*:\s*"((?:\\.|[^"\\])*)"', text)
        if m:
            try:
                msg = json.loads(f'"{m.group(1)}"')
            except ValueError:
                msg = m.group(1)
    if not msg:
        # Plain-text bodies stay, but drop pretty-printed JSON leftovers.
        if text[:1] in "{[":
            return ""
        msg = text
    msg = re.sub(r"\s+", " ", str(msg)).strip()
    return msg[:300]


def format_ai_http_error(
    code: int,
    detail: str = "",
    reason: str = "",
    *,
    tip: str = "",
) -> str:
    """One-line HTTP error for the AI panel: ``HTTP 503: <message>``."""
    msg = (
        summarize_ai_http_error_detail(detail)
        or str(reason or "").strip()
        or "request failed"
    )
    text = f"HTTP {int(code)}: {msg}"
    extra = str(tip or "").strip()
    if extra:
        if not text.endswith("."):
            text += "."
        text += " " + extra
    return text


def _ai_http_error_tip(code: int, detail: str = "", *, base_url: str = "") -> str:
    """Short remediation hint for OpenAI-compatible HTTP errors."""
    low = (detail or "").lower()
    host = (base_url or "").lower()
    if code in (401, 403):
        return (
            " Check authentication (Settings → AI → Sign in or API key, "
            "or OPENAI_API_KEY / GEMINI_API_KEY / OLLAMA_API_KEY)."
        )
    if code == 400 and (
        "valid api key" in low or "api key" in low and "invalid" in low
        or "multiple authentication" in low
    ):
        tip = (
            " Paste a Gemini key from https://aistudio.google.com/apikey into "
            "Settings → AI → API key (OpenAI-compatible), without a Bearer prefix. "
            "Click OK to save, then Test again."
        )
        if "generativelanguage" in host or "gemini" in host:
            tip += (
                " Use Bearer-only auth (AI Studio key). If the key starts with "
                "AQ., create a new key in AI Studio (non-AQ format) — Google's "
                "OpenAI-compat endpoint still rejects some AQ. keys. "
                "Do not use an OpenAI sk- key."
            )
        return tip
    if code == 429:
        tip = (
            " Rate/quota limit (RESOURCE_EXHAUSTED). Wait and retry, check "
            "https://aistudio.google.com/rate-limit (Gemini) or your provider dashboard."
        )
        if "gemini" in host or "generativelanguage" in host or "gemini" in low:
            tip += (
                " Try model gemini-flash-lite-latest (or gemini-flash-latest). "
                "Free quota for a pinned version is often 0 or closed to new "
                "users — enable billing or switch model/project."
            )
        return tip
    if code == 404:
        tip = " Check Base URL and model name for this provider."
        if "no longer available" in low or "not found" in low:
            tip += (
                " For Gemini, prefer the rolling aliases gemini-flash-lite-latest "
                "or gemini-flash-latest; pinned versions are retired over time."
            )
        return tip
    return ""


def ai_chat_completion(
    query: str = "",
    *,
    findings_text: str = "",
    metrics: Optional[Dict[str, Any]] = None,
    span: str = "",
    cores: Any = "",
    scope: str = "",
    base_url: str = DEFAULT_AI_BASE_URL,
    model: str = DEFAULT_AI_MODEL,
    api_key: str = "",
    response_language: str = DEFAULT_AI_RESPONSE_LANGUAGE,
    timeout_s: float = AI_CHAT_TIMEOUT_S,
    history: Optional[Sequence[Dict[str, str]]] = None,
    messages: Optional[List[Dict[str, Any]]] = None,
    tools: Optional[List[Dict[str, Any]]] = None,
    preset: str = "",
    tls_verify: bool = True,
    cancel_event: Optional[threading.Event] = None,
    on_response: Optional[Callable[[Any], None]] = None,
    log_mcp: bool = False,
) -> Dict[str, Any]:
    """One OpenAI-compatible ``/chat/completions`` round (non-streaming).

    Returns ``{"content", "tool_calls", "message", "usage"}``.
    """
    url_base = normalize_ai_base_url(base_url)
    url = url_base + "/chat/completions"
    chat_model = (model or DEFAULT_AI_MODEL).strip() or DEFAULT_AI_MODEL
    if not resolve_ai_api_key(api_key) and not is_local_ai_host(url_base):
        raise RuntimeError(AI_API_KEY_REQUIRED)
    if cancel_event is not None and cancel_event.is_set():
        raise OllamaCancelled("Stopped")
    if messages is None:
        messages = _build_chat_messages(
            query,
            findings_text=findings_text,
            metrics=metrics,
            span=span,
            cores=cores,
            scope=scope,
            response_language=response_language,
            history=history,
        )
    messages = normalize_tool_chat_messages(messages)
    if needs_gemini_thought_signatures(
            base_url=url_base, model=chat_model, preset=preset):
        messages = ensure_gemini_thought_signatures(messages)
    payload_obj: Dict[str, Any] = {
        "model": chat_model,
        "messages": messages,
        "stream": False,
    }
    use_tools = list(tools) if tools else []
    if use_tools:
        # Do not send tool_choice: Ollama/some proxies 400 on it and our old
        # retry then dropped *all* tools ("unknown" matched the error text).
        payload_obj["tools"] = use_tools

    def _post(body_obj: Dict[str, Any]) -> Dict[str, Any]:
        do_log = _want_ai_mcp_log(log_mcp)
        _log_ai_mcp("request", {"url": url, "body": body_obj}, enabled=do_log)
        payload = json.dumps(body_obj).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=payload,
            headers=ai_request_headers(api_key, base_url=url_base),
            method="POST",
        )
        try:
            resp = ai_urlopen(req, timeout_s, tls_verify=tls_verify)
        except urllib.error.HTTPError as exc:
            detail = ""
            try:
                detail = exc.read().decode("utf-8", errors="replace")[:400]
            except Exception:
                pass
            _log_ai_mcp("response_error", {
                "url": url,
                "http_code": int(exc.code),
                "detail": detail or str(exc.reason),
            }, enabled=do_log)
            tip = _ai_http_error_tip(exc.code, detail, base_url=url_base)
            err = RuntimeError(
                format_ai_http_error(
                    exc.code, detail, str(exc.reason or ""), tip=tip)
            )
            err.http_code = exc.code  # type: ignore[attr-defined]
            err.http_detail = detail  # type: ignore[attr-defined]
            raise err from exc
        except urllib.error.URLError as exc:
            if cancel_event is not None and cancel_event.is_set():
                raise OllamaCancelled("Stopped") from exc
            tip = _ai_ssl_error_tip(exc, tls_verify=tls_verify)
            tip += _ai_timeout_error_tip(exc, timeout_s=timeout_s)
            raise RuntimeError(
                f"Cannot reach OpenAI-compatible API at {url}.\n{exc.reason}{tip}"
            ) from exc
        except TimeoutError as exc:
            tip = _ai_timeout_error_tip(exc, timeout_s=timeout_s)
            raise RuntimeError(
                f"OpenAI-compatible request timed out after {timeout_s:.0f}s ({url}).{tip}"
            ) from exc

        if on_response is not None:
            try:
                on_response(resp)
            except Exception:
                pass
        try:
            if cancel_event is not None and cancel_event.is_set():
                raise OllamaCancelled("Stopped")
            raw = _read_http_body(resp, cancel_event=cancel_event).decode("utf-8")
            parsed = json.loads(raw)
            _log_ai_mcp("response", parsed, enabled=do_log)
            return parsed
        finally:
            try:
                resp.close()
            except Exception:
                pass
            if on_response is not None:
                try:
                    on_response(None)
                except Exception:
                    pass

    try:
        body = _post(payload_obj)
    except RuntimeError as exc:
        detail = str(getattr(exc, "http_detail", "") or exc).lower()
        code = int(getattr(exc, "http_code", 0) or 0)
        unsupported = any(
            s in detail for s in (
                "does not support tools",
                "does not support function",
                "tool calling is not supported",
                "unsupported tool",
                "unknown field: tools",
                'unknown field "tools"',
                "unknown field 'tools'",
            )
        )
        if use_tools and code in (400, 404, 422) and unsupported:
            payload_obj.pop("tools", None)
            payload_obj.pop("tool_choice", None)
            body = _post(payload_obj)
            use_tools = []
        else:
            raise

    def _parse_turn(resp_body: Any) -> Tuple[str, List[Dict[str, Any]], Dict[str, Any]]:
        choices = resp_body.get("choices") if isinstance(resp_body, dict) else None
        msg: Dict[str, Any] = {}
        choice0: Dict[str, Any] = {}
        if isinstance(choices, list) and choices and isinstance(choices[0], dict):
            choice0 = choices[0]
            raw_msg = choice0.get("message")
            if isinstance(raw_msg, dict):
                msg = raw_msg
            elif isinstance(resp_body.get("message"), dict):
                msg = resp_body["message"]
        content = assistant_message_text(msg, choice0)
        calls = extract_tool_calls(msg)
        if not calls and choice0.get("tool_calls"):
            calls = extract_tool_calls({"tool_calls": choice0.get("tool_calls")})
        text_calls = parse_tool_calls_from_text(content)
        calls = merge_tool_calls(calls, text_calls)
        if text_calls:
            content = strip_parsed_tool_markup(content)
        return content, calls, msg

    content, calls, msg = _parse_turn(body)
    if not content and not calls:
        # Gemini occasionally returns finish_reason=stop with 0 completion
        # tokens; one blind retry often recovers.
        body = _post(payload_obj)
        content, calls, msg = _parse_turn(body)
    if not content and not calls and use_tools:
        nudge = dict(payload_obj)
        nudge["messages"] = list(messages) + [{
            "role": "user",
            "content": (
                "Your previous reply was empty (no text and no tool call). "
                "Answer now with a short analysis, or call a tool."
            ),
        }]
        body = _post(nudge)
        content, calls, msg = _parse_turn(body)
    if not content and not calls:
        raise RuntimeError(
            empty_chat_completion_error(body, had_tools=bool(use_tools))
        )
    return {
        "content": content,
        "tool_calls": calls,
        "message": msg,
        "usage": chat_usage_from_response(body),
    }


def _benchmark_catalog_tool_payload(
    call: Dict[str, Any],
    case: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Host-side tool result for live ``ai-test`` (no GUI, no expected labels)."""
    catalog = (case or {}).get("catalog") if isinstance(case, dict) else {}
    if not isinstance(catalog, dict):
        catalog = {}
    name = str((call or {}).get("name") or "tool").strip() or "tool"
    return tool_result_payload(
        True,
        (
            f"Host recorded `{name}`. The catalog in Findings is the only evidence. "
            "Write your investigation conclusion in plain text now. "
            "Cite jump:TIME and Task[id] from the catalog. "
            "State confidence (High / Medium / Low)."
        ),
        tool=name,
        tasks=list(catalog.get("tasks") or []),
        times=list(catalog.get("times") or []),
        cursor_lo=catalog.get("cursor_lo"),
        cursor_hi=catalog.get("cursor_hi"),
    )


def _benchmark_needs_tool_followup(content: str, calls: Sequence[Any]) -> bool:
    """True when the first turn is a tool call, not a scored conclusion.

    Some models (Qwen 27B) put chain-of-thought / "I will call investigate"
    into ``content`` *and* emit ``tool_calls``. That text is not a conclusion
    (no Confidence: High/Medium/Low) and must not skip the host follow-up.
    """
    if not calls:
        return False
    blob = str(content or "").strip()
    if not blob:
        return True
    return not re.search(
        r"\bconfidence\s*:?\s*(high|medium|low)\b",
        blob,
        re.IGNORECASE,
    )


def live_benchmark_chat(
    query: str,
    findings_text: str = "",
    *,
    model: str = DEFAULT_AI_MODEL,
    case: Optional[Dict[str, Any]] = None,
    tools: Optional[List[Dict[str, Any]]] = None,
    base_url: str = DEFAULT_AI_BASE_URL,
    api_key: str = "",
    preset: str = "",
    tls_verify: bool = True,
    timeout_s: float = AI_CHAT_TIMEOUT_S,
) -> Dict[str, Any]:
    """One live benchmark turn, with a tool-result follow-up when needed.

    Gemini (and other tool-first models) often return ``tool_calls`` with empty
    ``content``. The viewer GUI executes the tool and continues the chat; the
    live scorer must do the same or finding/evidence/root-cause stay at 0.
    Models that already write a conclusion on the first turn are not called
    again.
    """
    t0 = time.time()
    messages = _build_chat_messages(query, findings_text=findings_text)
    collected: List[Dict[str, Any]] = []
    content = ""
    usage: Dict[str, Any] = {}
    error = ""

    def _one(*, use_tools: bool) -> Dict[str, Any]:
        return ai_chat_completion(
            "",
            findings_text="",
            model=model,
            base_url=base_url,
            api_key=api_key,
            preset=preset,
            tls_verify=tls_verify,
            timeout_s=timeout_s,
            messages=messages,
            tools=list(tools or []) if use_tools else [],
        )

    try:
        turn = _one(use_tools=bool(tools))
    except Exception as exc:
        return {
            "content": "",
            "tool_calls": [],
            "usage": {},
            "elapsed_s": time.time() - t0,
            "error": str(exc),
        }
    content = str((turn or {}).get("content") or "")
    calls = list((turn or {}).get("tool_calls") or [])
    usage = (turn or {}).get("usage") or {}
    collected.extend(c for c in calls if isinstance(c, dict))

    if _benchmark_needs_tool_followup(content, calls):
        asst = (turn or {}).get("message")
        if not isinstance(asst, dict) or str(asst.get("role") or "") != "assistant":
            asst = canonical_assistant_tool_message(content, calls)
        messages.append(asst)
        for i, call in enumerate(calls):
            if not isinstance(call, dict):
                continue
            payload = _benchmark_catalog_tool_payload(call, case)
            messages.append(tool_result_message(
                tool_call_id=str(call.get("id") or f"call_{i}"),
                name=str(call.get("name") or ""),
                content=format_tool_result_content(payload),
            ))
        messages.append({
            "role": "user",
            "content": (
                "Tool results are above. Do not call any more tools. "
                "Write your investigation conclusion in plain text now. "
                "Cite jump:TIME and Task[id] from the catalog. "
                "State confidence (High / Medium / Low)."
            ),
        })
        try:
            turn2 = _one(use_tools=False)
        except Exception as exc:
            error = str(exc)
            turn2 = {}
        if turn2:
            follow = str(turn2.get("content") or "")
            if follow.strip():
                content = follow
            more = list(turn2.get("tool_calls") or [])
            collected.extend(c for c in more if isinstance(c, dict))
            if turn2.get("usage"):
                usage = turn2.get("usage") or usage

    out: Dict[str, Any] = {
        "content": content,
        "tool_calls": collected,
        "usage": usage if isinstance(usage, dict) else {},
        "elapsed_s": time.time() - t0,
    }
    if error:
        out["error"] = error
    return out


def ai_chat(
    query: str,
    *,
    findings_text: str = "",
    metrics: Optional[Dict[str, Any]] = None,
    span: str = "",
    cores: Any = "",
    scope: str = "",
    base_url: str = DEFAULT_AI_BASE_URL,
    model: str = DEFAULT_AI_MODEL,
    api_key: str = "",
    response_language: str = DEFAULT_AI_RESPONSE_LANGUAGE,
    timeout_s: float = AI_CHAT_TIMEOUT_S,
    history: Optional[Sequence[Dict[str, str]]] = None,
    cancel_event: Optional[threading.Event] = None,
    on_response: Optional[Callable[[Any], None]] = None,
) -> str:
    """Call OpenAI-compatible ``/chat/completions`` (non-streaming)."""
    turn = ai_chat_completion(
        query,
        findings_text=findings_text,
        metrics=metrics,
        span=span,
        cores=cores,
        scope=scope,
        base_url=base_url,
        model=model,
        api_key=api_key,
        response_language=response_language,
        timeout_s=timeout_s,
        history=history,
        cancel_event=cancel_event,
        on_response=on_response,
    )
    text = str(turn.get("content") or "").strip()
    if text:
        return text
    calls = turn.get("tool_calls") or []
    if calls:
        return "\n".join(
            summarise_tool_call(c.get("name", ""), c.get("arguments") or {})
            for c in calls if isinstance(c, dict)
        )
    raise RuntimeError("The model returned an empty assistant message.")


def ai_list_models(
    base_url: str = DEFAULT_AI_BASE_URL,
    timeout_s: float = AI_LIST_MODELS_TIMEOUT_S,
    api_key: str = "",
    *,
    tls_verify: bool = True,
    log_mcp: bool = False,
) -> List[str]:
    """Return model ids from ``GET /models`` on an OpenAI-compatible API."""
    url_base = normalize_ai_base_url(base_url)
    url = url_base + "/models"
    do_log = _want_ai_mcp_log(log_mcp)
    _log_ai_mcp("request", {"method": "GET", "url": url}, enabled=do_log)
    req = urllib.request.Request(
        url, method="GET", headers=ai_request_headers(api_key, base_url=url_base),
    )
    try:
        with ai_urlopen(req, timeout_s, tls_verify=tls_verify) as resp:
            body = json.loads(resp.read().decode("utf-8"))
    except Exception as exc:
        _log_ai_mcp("response_error", {
            "method": "GET",
            "url": url,
            "error": str(exc),
        }, enabled=do_log)
        tip = _ai_ssl_error_tip(exc, tls_verify=tls_verify)
        raise RuntimeError(f"Cannot list models at {url}: {exc}{tip}") from exc
    _log_ai_mcp("response", {"url": url, "body": body}, enabled=do_log)
    models: List[str] = []
    rows = body.get("data") if isinstance(body, dict) else None
    for m in rows or []:
        name = m.get("id") if isinstance(m, dict) else None
        if name:
            models.append(str(name))
    return models


def _model_id(name: str) -> str:
    """Model id without Gemini's ``models/`` namespace prefix."""
    n = (name or "").strip()
    return n[7:] if n[:7].lower() == "models/" else n


def match_model_name(requested: str, available: Sequence[str]) -> Optional[str]:
    """Return the served model name matching *requested*, or None.

    Ollama reports ``name:tag`` while users often type just ``name``, and
    Gemini lists ids as ``models/<id>`` while the chat API takes either form.
    """
    want = _model_id(requested)
    if not want:
        return None
    names = [str(n) for n in available if n]
    if want in names:
        return want
    want_base = want.split(":", 1)[0]
    for n in names:
        served = _model_id(n)
        if served == want or served.startswith(want + ":"):
            return n
        served_base = served.split(":", 1)[0]
        if served_base == want or (":" not in want and served_base == want_base):
            return n
    return None


def ai_test_connection(
    base_url: str = DEFAULT_AI_BASE_URL,
    model: str = DEFAULT_AI_MODEL,
    *,
    api_key: str = "",
    tls_verify: bool = True,
    timeout_s: float = AI_TEST_TIMEOUT_S,
    on_progress: Optional[Callable[[str], None]] = None,
    log_mcp: bool = False,
) -> str:
    """List models, then run a tiny chat probe against the configured endpoint."""
    def _progress(msg: str) -> None:
        if on_progress is not None:
            try:
                on_progress(msg)
            except Exception:
                pass

    do_log = _want_ai_mcp_log(log_mcp)
    url_base = normalize_ai_base_url(base_url)
    model_name = (model or DEFAULT_AI_MODEL).strip() or DEFAULT_AI_MODEL
    key = resolve_ai_api_key(api_key)
    if not key and not is_local_ai_host(url_base):
        raise RuntimeError(AI_API_KEY_REQUIRED)

    _progress(f"1/3 Listing models at {url_base}…")
    served: List[str] = []
    listing_note = ""
    try:
        served = ai_list_models(
            url_base, timeout_s=min(AI_LIST_MODELS_TIMEOUT_S, timeout_s),
            api_key=key, tls_verify=tls_verify, log_mcp=do_log)
    except RuntimeError as exc:
        if is_local_ai_host(url_base):
            # Only name the canonical root when the user pointed elsewhere.
            wrong_root = (
                f" For a default Ollama install use {DEFAULT_AI_BASE_URL} "
                "(OpenAI-compatible endpoint)."
                if url_base != DEFAULT_AI_BASE_URL else ""
            )
            raise RuntimeError(
                f"{exc} Is `ollama serve` running?{wrong_root}"
            ) from exc
        listing_note = " (model list unavailable)"
    if served and match_model_name(model_name, served) is None:
        listing = ", ".join(served[:12])
        more = f" … +{len(served) - 12} more" if len(served) > 12 else ""
        raise RuntimeError(
            f"Model {model_name!r} is not served at {url_base}. "
            f"Available: {listing}{more}."
        )

    chat_url = url_base + "/chat/completions"
    _progress(
        f"2/3 Chat probe with {model_name} (first load can take a while)…"
    )
    body_obj = {
        "model": model_name,
        "stream": False,
        "messages": [{"role": "user", "content": CAPABILITY_CHAT_PROBE}],
        "max_tokens": 24,
    }
    _log_ai_mcp("request", {"url": chat_url, "body": body_obj}, enabled=do_log)
    payload = json.dumps(body_obj).encode("utf-8")
    req = urllib.request.Request(
        chat_url,
        data=payload,
        headers=ai_request_headers(key, base_url=url_base),
        method="POST",
    )
    try:
        with ai_urlopen(req, timeout_s, tls_verify=tls_verify) as resp:
            body = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = ""
        try:
            detail = exc.read().decode("utf-8", errors="replace")[:300]
        except Exception:
            pass
        _log_ai_mcp("response_error", {
            "url": chat_url,
            "http_code": int(exc.code),
            "detail": detail or str(exc.reason),
        }, enabled=do_log)
        tip = _ai_http_error_tip(exc.code, detail, base_url=url_base)
        raise RuntimeError(
            format_ai_http_error(
                exc.code, detail, str(exc.reason or ""), tip=tip)
        ) from exc
    except Exception as exc:
        _log_ai_mcp("response_error", {
            "url": chat_url,
            "error": str(exc),
        }, enabled=do_log)
        tip = _ai_ssl_error_tip(exc, tls_verify=tls_verify)
        tip += _ai_timeout_error_tip(exc, timeout_s=timeout_s)
        raise RuntimeError(
            f"Chat probe failed at {chat_url}: {exc}{tip}"
        ) from exc

    _log_ai_mcp("response", {"url": chat_url, "body": body}, enabled=do_log)
    reply = ""
    choices = body.get("choices") if isinstance(body, dict) else None
    if isinstance(choices, list) and choices:
        msg = choices[0].get("message") if isinstance(choices[0], dict) else None
        if isinstance(msg, dict):
            reply = str(msg.get("content") or "").strip()
    note = f" Probe reply: {reply[:40]!r}." if reply else ""
    tool_ok = None
    try:
        _progress(f"3/3 Tool-calling probe with {model_name}…")
        probe_obj = capability_probe_body(model_name)
        _log_ai_mcp("request", {"url": chat_url, "body": probe_obj}, enabled=do_log)
        probe_req = urllib.request.Request(
            chat_url,
            data=json.dumps(probe_obj).encode("utf-8"),
            headers=ai_request_headers(key, base_url=url_base),
            method="POST",
        )
        with ai_urlopen(probe_req, min(timeout_s, 20.0), tls_verify=tls_verify) as resp:
            probe_body = json.loads(resp.read().decode("utf-8"))
        _log_ai_mcp("response", {"url": chat_url, "body": probe_body}, enabled=do_log)
        tool_ok = tool_calling_from_chat_response(probe_body)
    except Exception as exc:
        _log_ai_mcp("response_error", {
            "url": chat_url, "error": f"tool probe: {exc}",
        }, enabled=do_log)
        tool_ok = None
        probe_body = None
    cap = infer_model_capability(
        model_name, chat_ok=True, tool_call_ok=tool_ok,
        chat_text=reply, tool_body=probe_body,
    )
    cap = merge_live_capability(
        cap, chat_text=reply, tool_body=probe_body, tool_ok=tool_ok,
    )
    cap_txt = format_capability_report(cap)
    return (
        f"Connected to {url_base}. Model {model_name} ready{listing_note}.{note}"
        + (f"\n\n{cap_txt}" if cap_txt else "")
    )


class _FlowLayout(QLayout):
    """Wrap chips like web ``display:flex; flex-wrap:wrap; gap:4px``.

    *break_before*: item indices that always start a new row (web ``.ai-tpl-row``).
    """

    def __init__(
        self,
        parent: Optional[QWidget] = None,
        spacing: int = 4,
        break_before: Optional[Tuple[int, ...]] = None,
    ) -> None:
        super().__init__(parent)
        self._items: List[Any] = []
        self._break_before = frozenset(int(i) for i in (break_before or ()))
        self.setContentsMargins(0, 0, 0, 0)
        self.setSpacing(int(spacing))

    def addItem(self, item) -> None:  # noqa: N802
        self._items.append(item)

    def count(self) -> int:
        return len(self._items)

    def itemAt(self, index: int):  # noqa: N802
        if 0 <= index < len(self._items):
            return self._items[index]
        return None

    def takeAt(self, index: int):  # noqa: N802
        if 0 <= index < len(self._items):
            return self._items.pop(index)
        return None

    def expandingDirections(self):  # noqa: N802
        return Qt.Orientation(0)

    def hasHeightForWidth(self) -> bool:  # noqa: N802
        return True

    def heightForWidth(self, width: int) -> int:  # noqa: N802
        return self._do_layout(QRect(0, 0, int(width), 0), True)

    def setGeometry(self, rect) -> None:  # noqa: N802
        super().setGeometry(rect)
        self._do_layout(rect, False)

    def sizeHint(self) -> QSize:  # noqa: N802
        return self.minimumSize()

    def minimumSize(self) -> QSize:  # noqa: N802
        size = QSize()
        for item in self._items:
            size = size.expandedTo(item.minimumSize())
        m = self.contentsMargins()
        size += QSize(m.left() + m.right(), m.top() + m.bottom())
        return size

    def _do_layout(self, rect, test_only: bool) -> int:
        left, top, right, bottom = self.getContentsMargins()
        effective = rect.adjusted(+left, +top, -right, -bottom)
        x = effective.x()
        y = effective.y()
        line_height = 0
        space = self.spacing()
        for idx, item in enumerate(self._items):
            hint = item.sizeHint()
            next_x = x + hint.width() + space
            wrap = line_height > 0 and (
                idx in self._break_before
                or next_x - space > effective.right() + 1
            )
            if wrap:
                x = effective.x()
                y = y + line_height + space
                next_x = x + hint.width() + space
                line_height = 0
            if not test_only:
                item.setGeometry(QRect(QPoint(x, y), hint))
            x = next_x
            line_height = max(line_height, hint.height())
        return y + line_height - rect.y() + bottom


def _ai_more_heading(label: str) -> QLabel:
    """Muted group label matching web ``.ai-more-heading``.

    Keep enabled: a disabled QLabel uses the Disabled palette (often a dark
    fill on macOS) and ignores ``color:`` QSS unless ``:disabled`` is set.
    """
    hdr = QLabel(label)
    hdr.setObjectName("aiMoreHeading")
    hdr.setTextInteractionFlags(Qt.TextInteractionFlag.NoTextInteraction)
    fusion = QStyleFactory.create("Fusion")
    if fusion is not None:
        hdr.setStyle(fusion)
    return hdr


def qt_wrap_tooltip(text: str, width_px: int = 320) -> str:
    """Rich-text tooltip that wraps at word boundaries at a readable width.

    Native macOS tips stay on one line. Character ``textwrap`` plus Qt's own
    wrap stacks two line-breaks, so a line often ends with a leftover word.
    A table cell ``width`` is the reliable QTipLabel constraint; Qt then wraps
    on spaces. Explicit newlines in the source stay as ``<br/>``.
    """
    raw = str(text or "").strip()
    if not raw:
        return ""
    parts = []
    for para in raw.split("\n"):
        chunk = para.strip()
        parts.append(html.escape(chunk) if chunk else "")
    body = "<br/>".join(parts)
    px = max(160, int(width_px))
    return (
        f'<html><body><table cellspacing="0" cellpadding="0"><tr>'
        f'<td width="{px}">{body}</td></tr></table></body></html>'
    )


def _ai_more_item(label: str, tooltip: str = "") -> QPushButton:
    """Flat menu row matching web ``.ai-more-item``."""
    btn = QPushButton(label)
    btn.setObjectName("aiMoreItem")
    btn.setFlat(True)
    btn.setAutoDefault(False)
    btn.setDefault(False)
    btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
    btn.setCursor(Qt.CursorShape.PointingHandCursor)
    btn.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
    btn.setMinimumHeight(22)
    fusion = QStyleFactory.create("Fusion")
    if fusion is not None:
        btn.setStyle(fusion)
    if tooltip:
        btn.setToolTip(qt_wrap_tooltip(tooltip))
    return btn


def _ai_more_col(title: str) -> QWidget:
    """One More-menu column matching web ``.ai-more-col``."""
    col = QWidget()
    col.setObjectName("aiMoreCol")
    fusion = QStyleFactory.create("Fusion")
    if fusion is not None:
        col.setStyle(fusion)
    lay = QVBoxLayout(col)
    lay.setContentsMargins(0, 0, 0, 0)
    lay.setSpacing(0)
    lay.addWidget(_ai_more_heading(title))
    return col


def _clear_layout(layout) -> None:
    while layout.count():
        item = layout.takeAt(0)
        w = item.widget()
        if w is not None:
            w.setParent(None)
            w.deleteLater()


# Chip / More-menu colors match web `.ai-tpl-btn` / `.ai-more-item` (enabled vs disabled).
_AI_TPL_DISABLED_COLOR = "#8a96a8"
_AI_CHIP_MIN_HEIGHT = 28  # match web `.ai-tpl-btn { min-height: 28px }`


def _ai_chrome_colors(is_dark: bool) -> dict:
    if is_dark:
        return dict(
            panel="#1a2230",
            btn="#243044",
            text="#e8eef7",
            muted=_AI_TPL_DISABLED_COLOR,
            border="#3a4658",
            hover="#243044",
            accent="#2a6fb2",
            chip_hover="#dbe2ea",
        )
    return dict(
        panel="#F5F5F5",
        btn="#E8E8E8",
        text="#1E1E1E",
        muted="#666666",
        border="#DDDDDD",
        hover="#E0E8F0",
        accent="#0066CC",
        chip_hover="#1E1E1E",
    )


def _ai_tpl_btn_style(is_dark: bool = True) -> str:
    c = _ai_chrome_colors(is_dark)
    muted = c["muted"]
    return (
        "QPushButton {"
        f"  color: {c['text']};"
        f"  background: {c['btn']};"
        f"  border: 1px solid {c['border']};"
        "  border-radius: 6px;"
        "  padding: 4px 8px;"
        "}"
        "QPushButton:disabled {"
        f"  color: {muted};"
        f"  background: {c['panel']};"
        f"  border-color: {c['border']};"
        "}"
        "QPushButton:hover:!disabled {"
        f"  border-color: {c['accent']};"
        "}"
    )


def _ai_more_menu_style(is_dark: bool = True) -> str:
    c = _ai_chrome_colors(is_dark)
    muted = c["muted"]
    return (
        "QFrame#aiMoreMenu {"
        f"  background: {c['panel']};"
        f"  border: 1px solid {c['border']};"
        "  border-radius: 7px;"
        "}"
        "QWidget#aiMoreCol { min-width: 168px; }"
        "QLabel#aiMoreHeading, QLabel#aiMoreHeading:disabled {"
        f"  color: {muted};"
        f"  background: {c['panel']};"
        "  font-size: 11px;"
        "  font-weight: 600;"
        "  padding: 6px 10px 2px;"
        "}"
        "QPushButton#aiMoreItem {"
        f"  color: {c['text']};"
        f"  background: {c['panel']};"
        "  border: none;"
        "  border-radius: 4px;"
        "  padding: 5px 10px;"
        "  min-height: 22px;"
        "  text-align: left;"
        "}"
        "QPushButton#aiMoreItem:hover:!disabled {"
        f"  background: {c['hover']};"
        "}"
        f"QPushButton#aiMoreItem:disabled {{ color: {muted}; }}"
    )


_AI_TPL_BTN_STYLE = _ai_tpl_btn_style(True)
_AI_MORE_MENU_STYLE = _ai_more_menu_style(True)


def _qtextline_cursor_x(line, pos: int) -> float:
    """Horizontal caret x. PySide ``cursorToX`` often returns ``(x, cursorPos)``."""
    raw = line.cursorToX(int(pos))
    if isinstance(raw, (tuple, list)):
        return float(raw[0]) if raw else 0.0
    return float(raw or 0.0)


def create_ai_assistant_panel(
    parent=None,
    *,
    get_context: Optional[Callable[[], Dict[str, Any]]] = None,
    get_settings: Optional[Callable[[], Dict[str, str]]] = None,
    on_open_settings: Optional[Callable[[], None]] = None,
    on_save_settings: Optional[Callable[[Dict[str, str]], None]] = None,
    on_jump: Optional[Callable[[float], None]] = None,
    on_range: Optional[Callable[[float, float], None]] = None,
    on_highlight: Optional[Callable[[str], None]] = None,
    on_execute_tools: Optional[Callable[[List[Dict[str, Any]]], List[Dict[str, Any]]]] = None,
    on_undo_tools: Optional[Callable[[], None]] = None,
    on_gui_state: Optional[Callable[[], Dict[str, Any]]] = None,
    get_loaded_tabs: Optional[Callable[[], List[Dict[str, Any]]]] = None,
    build_compare_context: Optional[
        Callable[[int, int], Dict[str, Any]]
    ] = None,
):
    """Build the right-panel AI chat widget (requires Qt bindings).

    *get_loaded_tabs*: ``[{"index": int, "name": str}, ...]`` for Trace Compare.
    *build_compare_context*: ``(idx_a, idx_b) ->`` context dict like *get_context*
    with Trace Compare CSV in ``findings_text``.
    """

    class _AiLanguageDialog(QDialog):
        def __init__(self, current: str, parent_w=None) -> None:
            super().__init__(parent_w)
            self.setWindowTitle("AI response language")
            self.setModal(True)
            self.setMinimumWidth(360)
            lay = QVBoxLayout(self)
            lay.addWidget(QLabel("Preferred language for assistant replies:"))
            self._combo = QComboBox()
            self._combo.addItems(list(AI_RESPONSE_LANGUAGES))
            cur = (current or DEFAULT_AI_RESPONSE_LANGUAGE).strip()
            idx = self._combo.findText(cur)
            if idx < 0:
                self._combo.addItem(cur)
                idx = self._combo.findText(cur)
            self._combo.setCurrentIndex(max(0, idx))
            self._combo.setSizeAdjustPolicy(
                QComboBox.SizeAdjustPolicy.AdjustToContents)
            fm = self._combo.fontMetrics()
            lang_w = max((fm.horizontalAdvance(s) for s in AI_RESPONSE_LANGUAGES), default=120) + 48
            self._combo.setMinimumWidth(max(lang_w, 280))
            lay.addWidget(self._combo)
            buttons = QDialogButtonBox(
                QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
            )
            buttons.accepted.connect(self.accept)
            buttons.rejected.connect(self.reject)
            lay.addWidget(buttons)

        def selected_language(self) -> str:
            return self._combo.currentText().strip() or DEFAULT_AI_RESPONSE_LANGUAGE

    class _AiComparePickDialog(QDialog):
        """Choose two loaded tabs for the Trace Compare AI template."""

        def __init__(self, tabs: List[Dict[str, Any]], parent_w=None) -> None:
            super().__init__(parent_w)
            self.setWindowTitle("AI Trace Compare")
            self.setModal(True)
            self.setMinimumWidth(420)
            lay = QVBoxLayout(self)
            lay.addWidget(QLabel("Choose two open traces to compare:"))
            row = QHBoxLayout()
            row.addWidget(QLabel("Trace A:"))
            self._combo_a = QComboBox()
            row.addWidget(self._combo_a, 1)
            row.addWidget(QLabel("Trace B:"))
            self._combo_b = QComboBox()
            row.addWidget(self._combo_b, 1)
            lay.addLayout(row)
            for t in tabs:
                label = str(t.get("name") or f"Tab {t.get('index', '?')}")
                idx = int(t.get("index", 0))
                self._combo_a.addItem(label, idx)
                self._combo_b.addItem(label, idx)
            if len(tabs) >= 2:
                self._combo_b.setCurrentIndex(min(1, len(tabs) - 1))
            buttons = QDialogButtonBox(
                QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
            )
            ok_btn = buttons.button(QDialogButtonBox.StandardButton.Ok)
            if ok_btn is not None:
                ok_btn.setText("Compare")
            buttons.accepted.connect(self.accept)
            buttons.rejected.connect(self.reject)
            lay.addWidget(buttons)

        def selected_indices(self) -> Tuple[int, int]:
            return (
                int(self._combo_a.currentData()),
                int(self._combo_b.currentData()),
            )

    class _OllamaWorker(QObject):
        """Runs ai_chat on a plain Python thread; emits to the GUI thread.

        Avoids QThread + moveToThread + deleteLater, which can SIGSEGV in
        PySide when DeferredDelete runs on the worker thread.
        """

        finished = Signal(str)
        failed = Signal(str)
        cancelled = Signal()

        def __init__(self, parent: QObject, kwargs: dict) -> None:
            super().__init__(parent)
            self._kwargs = kwargs
            self._cancel = threading.Event()
            self._resp = None
            self._resp_lock = threading.Lock()

        def cancel(self) -> None:
            self._cancel.set()
            with self._resp_lock:
                resp = self._resp
            if resp is not None:
                try:
                    resp.close()
                except Exception:
                    pass

        def _set_resp(self, resp: Any) -> None:
            with self._resp_lock:
                self._resp = resp

        def start(self) -> None:
            threading.Thread(target=self._run, name="ai-chat", daemon=True).start()

        def _run(self) -> None:
            try:
                turn = ai_chat_completion(
                    **self._kwargs,
                    cancel_event=self._cancel,
                    on_response=self._set_resp,
                )
                if self._cancel.is_set():
                    self.cancelled.emit()
                else:
                    self.finished.emit(json.dumps(turn, default=str))
            except OllamaCancelled:
                self.cancelled.emit()
            except Exception as exc:
                if self._cancel.is_set():
                    self.cancelled.emit()
                else:
                    self.failed.emit(str(exc))

    class AiAssistantPanel(QWidget):
        def __init__(self) -> None:
            super().__init__(parent)
            self.setMinimumWidth(0)
            self._busy = False
            self._worker: Optional[_OllamaWorker] = None
            self._entries: List[Any] = []
            self._chat_messages: List[Dict[str, Any]] = []
            self._tool_round = 0
            self._pending_batches: Dict[str, Dict[str, Any]] = {}
            self._batch_seq = 0
            self._cost_meter: Dict[str, Any] = empty_cost_meter()
            self._cost_started = 0.0

            root = QVBoxLayout(self)
            root.setContentsMargins(6, 6, 6, 6)
            root.setSpacing(6)

            header_host = QWidget()
            header_host.setObjectName("aiHeader")
            header_row = _FlowLayout(header_host, spacing=8)
            title = QLabel("AI Assistant")
            title.setStyleSheet("font-weight:600;")
            header_row.addWidget(title)
            self._auth_chip = QPushButton("")
            self._auth_chip.setObjectName("ai_auth_chip")
            self._auth_chip.setCursor(Qt.CursorShape.PointingHandCursor)
            self._auth_chip.setToolTip("Open Settings → AI to sign in or change the API key")
            self._auth_chip.setSizePolicy(
                QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Fixed)
            self._auth_chip.setStyleSheet(
                "QPushButton#ai_auth_chip {"
                "  background: transparent; color: #8b98a8;"
                "  border: 1px solid #3a4658; border-radius: 10px;"
                "  padding: 1px 8px; font-size: 11px;"
                "}"
                "QPushButton#ai_auth_chip:hover { color: #dbe2ea; border-color: #5b9bd5; }"
            )
            self._auth_chip.clicked.connect(self._on_auth_chip)
            header_row.addWidget(self._auth_chip)
            self._privacy_chip = QPushButton("")
            self._privacy_chip.setObjectName("ai_privacy_chip")
            self._privacy_chip.setCursor(Qt.CursorShape.PointingHandCursor)
            self._privacy_chip.setToolTip(
                "Trace privacy for the current AI endpoint")
            self._privacy_chip.setSizePolicy(
                QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Fixed)
            self._privacy_chip.setStyleSheet(
                "QPushButton#ai_privacy_chip {"
                "  background: transparent; color: #8b98a8;"
                "  border: 1px solid #3a4658; border-radius: 10px;"
                "  padding: 1px 8px; font-size: 11px;"
                "}"
                "QPushButton#ai_privacy_chip:hover { color: #dbe2ea; "
                "border-color: #5b9bd5; }"
            )
            self._privacy_chip.clicked.connect(self._on_auth_chip)
            header_row.addWidget(self._privacy_chip)
            root.addWidget(header_host)

            # Match web `.ai-header-actions { flex-wrap }`. objectName
            # "aiActions" is excluded from dock width-relax (Ignored policy
            # was collapsing these buttons to 0 width).
            actions_host = QWidget()
            actions_host.setObjectName("aiActions")
            actions_row = _FlowLayout(actions_host, spacing=4)

            def _ai_action_btn(label: str, tip: str, *, primary: bool = False) -> QPushButton:
                btn = QPushButton(label)
                btn.setObjectName("ai_action_btn")
                btn.setToolTip(tip)
                btn.setCursor(Qt.CursorShape.PointingHandCursor)
                btn.setSizePolicy(QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Fixed)
                btn.setMinimumHeight(24)
                if primary:
                    btn.setDefault(True)
                    btn.setStyleSheet(
                        "QPushButton#ai_action_btn {"
                        "  background: #2a6fb2; color: #ffffff;"
                        "  border: 1px solid #1a5a9a; border-radius: 3px;"
                        "  padding: 3px 10px; font-weight: 600;"
                        "}"
                        "QPushButton#ai_action_btn:hover { background: #1a5a9a; }"
                        "QPushButton#ai_action_btn:disabled {"
                        "  background: #555555; color: #bbbbbb; border-color: #555555;"
                        "}"
                    )
                return btn

            self._clear_btn = _ai_action_btn("Clear", "Clear the conversation log")
            self._clear_btn.clicked.connect(self.clear_conversation)
            actions_row.addWidget(self._clear_btn)
            self._lang_btn = _ai_action_btn(
                "Language\u2026", "Preferred language for assistant replies")
            self._lang_btn.clicked.connect(self._choose_language)
            actions_row.addWidget(self._lang_btn)
            self._settings_btn = _ai_action_btn(
                "Settings\u2026",
                "Configure the AI preset, endpoint, and model")
            self._settings_btn.clicked.connect(self._open_settings)
            actions_row.addWidget(self._settings_btn)

            root.addWidget(actions_host)

            split_top = QWidget()
            split_top.setObjectName("aiSplitTop")
            top_lay = QVBoxLayout(split_top)
            top_lay.setContentsMargins(0, 0, 0, 0)
            top_lay.setSpacing(6)
            self._split_top = split_top

            split_bottom = QWidget()
            split_bottom.setObjectName("aiSplitBottom")
            split_bottom.setMinimumHeight(64)
            bottom_lay = QVBoxLayout(split_bottom)
            bottom_lay.setContentsMargins(0, 0, 0, 0)
            bottom_lay.setSpacing(0)
            self._split_bottom = split_bottom

            self._investigation_plan: Optional[Dict[str, Any]] = None
            self._evidence_payload: Optional[Dict[str, Any]] = None
            self._interpreted_query: Optional[Dict[str, Any]] = None
            self._skip_interpret = False
            self._active_template_id = ""

            self._log = QTextBrowser()
            self._log.setReadOnly(True)
            self._log.setOpenExternalLinks(False)
            self._log.setOpenLinks(False)
            self._log.setPlaceholderText(
                "Conversation appears here\u2026\n"
                "Uses Analysis Findings for the current Statistics scope. "
                "Configure the endpoint in Settings \u2192 AI."
            )
            self._log.setMinimumHeight(80)
            self._log.setSizePolicy(
                QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
            self._log.document().setDefaultStyleSheet(_AI_LOG_STYLE)
            self._log.anchorClicked.connect(self._on_jump_link)
            self._log.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
            self._log.customContextMenuRequested.connect(self._show_log_menu)
            self._log.viewport().installEventFilter(self)
            top_lay.addWidget(self._log, 1)

            self._plan_host = QWidget()
            plan_row = QHBoxLayout(self._plan_host)
            plan_row.setContentsMargins(0, 0, 0, 0)
            plan_row.setSpacing(0)
            self._plan_view = QLabel("")
            self._plan_view.setWordWrap(False)
            self._plan_view.setTextInteractionFlags(
                Qt.TextInteractionFlag.NoTextInteraction)
            self._plan_view.setSizePolicy(
                QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            self._plan_view.setStyleSheet(
                "color:#8a96a8;font-size:11px;padding:1px 0;"
            )
            plan_row.addWidget(self._plan_view)
            self._plan_host.hide()
            top_lay.addWidget(self._plan_host)

            mode_host = QWidget()
            self._mode_host = mode_host
            mode_host.setObjectName("aiModes")
            mode_host.setSizePolicy(
                QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Preferred)
            mode_host.setStyleSheet(_AI_TPL_BTN_STYLE)
            mode_row = _FlowLayout(mode_host, spacing=4)
            self._mode_btns: List[QPushButton] = []
            for mid in INVESTIGATION_MODES:
                btn = QPushButton(INVESTIGATION_MODE_LABELS.get(mid, mid.title()))
                btn.setToolTip(qt_wrap_tooltip(investigation_mode_prompt(mid)))
                btn.setSizePolicy(
                    QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Fixed)
                btn.setMinimumHeight(_AI_CHIP_MIN_HEIGHT)
                btn.clicked.connect(
                    lambda _=False, m=mid: self._run_investigation_mode(m)
                )
                mode_row.addWidget(btn)
                self._mode_btns.append(btn)
            top_lay.addWidget(mode_host)

            tpl_host = QWidget()
            self._tpl_host = tpl_host
            tpl_host.setObjectName("aiTemplates")
            tpl_host.setSizePolicy(
                QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Preferred)
            tpl_host.setStyleSheet(_AI_TPL_BTN_STYLE)
            _lead_ids, _last_ids = ai_template_primary_rows()
            tpl_row = _FlowLayout(
                tpl_host, spacing=4, break_before=(len(_lead_ids),))

            self._template_btns: List[QPushButton] = []
            self._template_actions: Dict[str, Any] = {}
            self._compare_btn: Optional[QWidget] = None
            self._smp_only_btns: Dict[str, QWidget] = {}

            def _bind_template_ctrl(tid: str, ctrl) -> None:
                if tid == AI_COMPARE_TEMPLATE_ID:
                    self._compare_btn = ctrl
                if tid in AI_SMP_ONLY_TEMPLATE_IDS:
                    self._smp_only_btns[tid] = ctrl

            for _tid in _lead_ids + _last_ids:
                item = ai_template_by_id(_tid)
                if item is None:
                    continue
                _tid, label, prompt = item
                btn = QPushButton(label)
                btn.setToolTip(qt_wrap_tooltip(prompt))
                btn.setSizePolicy(
                    QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Fixed)
                btn.setMinimumHeight(_AI_CHIP_MIN_HEIGHT)
                btn.clicked.connect(
                    lambda _=False, t=_tid, p=prompt: self._use_template(t, p)
                )
                tpl_row.addWidget(btn)
                self._template_btns.append(btn)
                _bind_template_ctrl(_tid, btn)

            more_btn = QPushButton("More templates\u2026")
            more_btn.setToolTip(qt_wrap_tooltip(
                "Uses Analysis Findings for the current Statistics scope. "
                "Configure the endpoint in Settings \u2192 AI."
            ))
            more_btn.setSizePolicy(
                QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Fixed)
            more_btn.setMinimumHeight(_AI_CHIP_MIN_HEIGHT)
            more_menu = QFrame(self, Qt.WindowType.Popup)
            more_menu.setObjectName("aiMoreMenu")
            fusion = QStyleFactory.create("Fusion")
            if fusion is not None:
                more_menu.setStyle(fusion)
            more_menu.setStyleSheet(_AI_MORE_MENU_STYLE)
            more_menu.setAutoFillBackground(True)
            more_menu.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
            more_menu.setMinimumWidth(360)
            more_grid = QGridLayout(more_menu)
            more_grid.setContentsMargins(4, 4, 4, 4)
            more_grid.setHorizontalSpacing(8)
            more_grid.setVerticalSpacing(0)
            more_grid.setSizeConstraint(QLayout.SizeConstraint.SetFixedSize)
            for i, (group_label, ids) in enumerate(AI_TEMPLATE_MENU_GROUPS):
                col = _ai_more_col(group_label)
                col_lay = col.layout()
                for _tid in ids:
                    item = ai_template_by_id(_tid)
                    if item is None:
                        continue
                    _tid, label, prompt = item
                    act = _ai_more_item(label, prompt)
                    act.clicked.connect(
                        lambda _=False, t=_tid, p=prompt: self._on_more_template(t, p)
                    )
                    col_lay.addWidget(act)
                    self._template_actions[_tid] = act
                    _bind_template_ctrl(_tid, act)
                col_lay.addStretch(1)
                more_grid.addWidget(
                    col, i // 2, i % 2, Qt.AlignmentFlag.AlignTop)
            n_groups = len(AI_TEMPLATE_MENU_GROUPS)
            self._investigation_col = _ai_more_col("Investigations")
            more_grid.addWidget(
                self._investigation_col,
                n_groups // 2, n_groups % 2,
                Qt.AlignmentFlag.AlignTop,
            )
            self._investigation_template_actions: Dict[str, Any] = {}
            self._more_menu = more_menu
            self._more_btn = more_btn
            self._more_reclick_guard = False
            self._save_investigation_template_action = None
            self._save_knowledge_action = None
            self._rebuild_investigation_menu()
            more_btn.clicked.connect(self._toggle_more_menu)
            more_menu.installEventFilter(self)
            tpl_row.addWidget(more_btn)
            top_lay.addWidget(tpl_host)

            self.refresh_template_availability()

            self._tool_bar = QWidget()
            tool_row = QHBoxLayout(self._tool_bar)
            tool_row.setContentsMargins(0, 0, 0, 0)
            tool_row.setSpacing(6)
            self._apply_tools_btn = QPushButton("Apply GUI actions")
            self._apply_tools_btn.setToolTip(
                "Run the pending viewer tools from the last reply")
            self._apply_tools_btn.clicked.connect(self._apply_pending_tools)
            self._skip_tools_btn = QPushButton("Skip")
            self._skip_tools_btn.clicked.connect(self._skip_pending_tools)
            self._undo_tools_btn = QPushButton("Undo last actions")
            self._undo_tools_btn.clicked.connect(self._undo_last_tools)
            tool_row.addWidget(self._apply_tools_btn)
            tool_row.addWidget(self._skip_tools_btn)
            tool_row.addWidget(self._undo_tools_btn)
            tool_row.addStretch(1)
            self._tool_bar.hide()
            top_lay.addWidget(self._tool_bar)

            self._input = QPlainTextEdit()
            self._input.setObjectName("aiInput")
            self._input.setPlaceholderText("Ask about this trace\u2026 (Ctrl/Cmd+Enter to send)")
            self._input.setMinimumHeight(64)
            self._input.setSizePolicy(
                QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
            self._input.setViewportMargins(0, 0, 44, 0)
            self._input.installEventFilter(self)
            self._input.textChanged.connect(self._refresh_send_btn)

            composer = QWidget()
            composer.setObjectName("aiComposer")
            composer_lay = QVBoxLayout(composer)
            composer_lay.setContentsMargins(0, 0, 0, 0)
            composer_lay.setSpacing(0)
            composer_lay.addWidget(self._input)

            def _ai_icon_btn(name: str, tip: str) -> QPushButton:
                btn = QPushButton()
                btn.setObjectName(name)
                btn.setToolTip(tip)
                btn.setCursor(Qt.CursorShape.PointingHandCursor)
                btn.setFixedSize(28, 28)
                btn.setIconSize(QSize(16, 16))
                btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
                btn.setStyleSheet(
                    f"QPushButton#{name} {{"
                    "  background: #2a6fb2; border: none; border-radius: 14px;"
                    "}"
                    f"QPushButton#{name}:hover {{ background: #1a5a9a; }}"
                    f"QPushButton#{name}:disabled {{"
                    "  background: #555555;"
                    "}"
                )
                return btn

            icons = QWidget(composer)
            icons.setObjectName("aiComposerIcons")
            icon_row = QHBoxLayout(icons)
            icon_row.setContentsMargins(0, 0, 0, 0)
            icon_row.setSpacing(0)
            self._icon_send = _svg_icon(AI_SEND_ICON_PATH, "#ffffff", 16)
            self._icon_stop = _svg_icon(AI_STOP_ICON_PATH, "#ffffff", 16)
            self._send_btn = _ai_icon_btn(
                "aiSendBtn", "Send the question (Ctrl/Cmd+Enter)")
            self._send_btn.setIcon(self._icon_send)
            self._send_btn.clicked.connect(self._on_composer_action)
            icon_row.addWidget(self._send_btn)
            self._composer = composer
            self._composer_icons = icons
            composer.installEventFilter(self)
            composer.setSizePolicy(
                QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
            bottom_lay.addWidget(composer, 1)
            QTimer.singleShot(0, self._place_composer_icons)

            split = QSplitter(Qt.Orientation.Vertical)
            split.setObjectName("aiSplit")
            split.setChildrenCollapsible(False)
            split.setHandleWidth(6)
            split.addWidget(split_top)
            split.addWidget(split_bottom)
            split.setStretchFactor(0, 1)
            split.setStretchFactor(1, 0)
            split.splitterMoved.connect(self._on_ai_split_moved)
            self._split = split
            self._split_ready = False
            root.addWidget(split, 1)
            QTimer.singleShot(0, self._restore_ai_split)

            self._status = QLabel("")
            self._status.setObjectName("aiStatus")
            self._status.setStyleSheet("color:#999;font-size:11px;")
            self._status.setWordWrap(True)
            root.addWidget(self._status)

            self._usage = QLabel("")
            self._usage.setObjectName("aiUsageBar")
            self._usage.setStyleSheet(
                "color:#8a96a8;font-size:11px;padding:2px 0;"
                "border-top:1px solid #3a4658;"
            )
            self._usage.setTextInteractionFlags(
                Qt.TextInteractionFlag.TextSelectableByMouse)
            root.addWidget(self._usage)
            self._refresh_usage()

            self._auth_cta = QWidget()
            cta_row = QHBoxLayout(self._auth_cta)
            cta_row.setContentsMargins(0, 0, 0, 0)
            cta_row.setSpacing(6)
            self._auth_cta_signin = QPushButton("Sign in…")
            self._auth_cta_signin.setToolTip("Open the provider sign-in page")
            self._auth_cta_signin.clicked.connect(self._open_signin_page)
            self._auth_cta_settings = QPushButton("Settings…")
            self._auth_cta_settings.clicked.connect(self._open_settings)
            cta_row.addWidget(self._auth_cta_signin)
            cta_row.addWidget(self._auth_cta_settings)
            cta_row.addStretch(1)
            self._auth_cta.hide()
            self._auth_forced = False
            root.addWidget(self._auth_cta)
            self._refresh_auth_chip()

            self._refresh_send_btn()
            wnd = self.window()
            is_dark = bool(getattr(wnd, "_is_dark", True))
            self._is_dark = is_dark
            self.apply_theme(is_dark)

        def apply_theme(self, is_dark: bool) -> None:
            """Match AI chrome (More menu, chips, composer, log) to the app theme."""
            self._is_dark = bool(is_dark)
            c = _ai_chrome_colors(self._is_dark)
            if getattr(self, "_mode_host", None) is not None:
                self._mode_host.setStyleSheet(_ai_tpl_btn_style(self._is_dark))
            if getattr(self, "_tpl_host", None) is not None:
                self._tpl_host.setStyleSheet(_ai_tpl_btn_style(self._is_dark))
            self._paint_more_menu()
            chip = (
                "QPushButton#%s {"
                "  background: transparent; color: %s;"
                "  border: 1px solid %s; border-radius: 10px;"
                "  padding: 1px 8px; font-size: 11px;"
                "}"
                "QPushButton#%s:hover { color: %s; border-color: %s; }"
            )
            if getattr(self, "_auth_chip", None) is not None:
                self._auth_chip.setStyleSheet(chip % (
                    "ai_auth_chip", c["muted"], c["border"],
                    "ai_auth_chip", c["chip_hover"], c["accent"],
                ))
            if getattr(self, "_privacy_chip", None) is not None:
                self._privacy_chip.setStyleSheet(chip % (
                    "ai_privacy_chip", c["muted"], c["border"],
                    "ai_privacy_chip", c["chip_hover"], c["accent"],
                ))
            if getattr(self, "_plan_view", None) is not None:
                self._plan_view.setStyleSheet(
                    f"color:{c['muted']};font-size:11px;padding:1px 0;"
                )
            if getattr(self, "_status", None) is not None:
                self._status.setStyleSheet(f"color:{c['muted']};font-size:11px;")
            if getattr(self, "_usage", None) is not None:
                self._usage.setStyleSheet(
                    f"color:{c['muted']};font-size:11px;padding:2px 0;"
                    f"border-top:1px solid {c['border']};"
                )
            if getattr(self, "_split", None) is not None:
                self._split.setStyleSheet(
                    "QSplitter::handle { background: %s; }"
                    "QSplitter::handle:hover { background: %s; }"
                    "QSplitter::handle:vertical { height: 6px; }"
                    % (c["border"], c["accent"])
                )
            inp = getattr(self, "_input", None)
            if inp is not None:
                pal = inp.palette()
                pal.setColor(QPalette.Base, QColor(c["panel"]))
                pal.setColor(QPalette.Text, QColor(c["text"]))
                pal.setColor(QPalette.Window, QColor(c["panel"]))
                inp.setPalette(pal)
                inp.setStyleSheet(
                    f"QPlainTextEdit#aiInput {{"
                    f"  background: {c['panel']}; color: {c['text']};"
                    f"  border: 1px solid {c['border']}; border-radius: 6px;"
                    "}"
                )
            log = getattr(self, "_log", None)
            if log is not None:
                pal = log.palette()
                pal.setColor(QPalette.Base, QColor(c["panel"]))
                pal.setColor(QPalette.Text, QColor(c["text"]))
                pal.setColor(QPalette.Window, QColor(c["panel"]))
                log.setPalette(pal)
                log.document().setDefaultStyleSheet(_ai_log_style(self._is_dark))
                if getattr(self, "_entries", None):
                    self._refresh_log()

        def _paint_more_menu(self) -> None:
            menu = getattr(self, "_more_menu", None)
            if menu is None:
                return
            is_dark = bool(getattr(self, "_is_dark", True))
            c = _ai_chrome_colors(is_dark)
            menu.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
            menu.setAutoFillBackground(True)
            menu.setStyleSheet(_ai_more_menu_style(is_dark))
            pal = menu.palette()
            bg = QColor(c["panel"])
            fg = QColor(c["text"])
            muted = QColor(c["muted"])
            for group in (QPalette.ColorGroup.Active, QPalette.ColorGroup.Inactive,
                          QPalette.ColorGroup.Disabled):
                pal.setColor(group, QPalette.ColorRole.Window, bg)
                pal.setColor(group, QPalette.ColorRole.Base, bg)
                pal.setColor(group, QPalette.ColorRole.Button, bg)
                role_fg = muted if group == QPalette.ColorGroup.Disabled else fg
                pal.setColor(group, QPalette.ColorRole.WindowText, role_fg)
                pal.setColor(group, QPalette.ColorRole.ButtonText, role_fg)
                pal.setColor(group, QPalette.ColorRole.Text, role_fg)
            menu.setPalette(pal)
            item_ss = (
                f"QPushButton#aiMoreItem {{"
                f"  color: {c['text']}; background: {c['panel']};"
                "  border: none; border-radius: 4px;"
                "  padding: 5px 10px; min-height: 22px; text-align: left;"
                "}"
                f"QPushButton#aiMoreItem:hover:!disabled {{ background: {c['hover']}; }}"
                f"QPushButton#aiMoreItem:disabled {{ color: {c['muted']}; "
                f"background: {c['panel']}; }}"
            )
            heading_ss = (
                f"QLabel#aiMoreHeading, QLabel#aiMoreHeading:disabled {{"
                f"  color: {c['muted']}; background: {c['panel']};"
                "  font-size: 11px; font-weight: 600; padding: 6px 10px 2px;"
                "}"
            )
            for w in menu.findChildren(QWidget):
                w.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
                w.setPalette(pal)
                if w.objectName() == "aiMoreItem":
                    w.setAutoFillBackground(True)
                    w.setStyleSheet(item_ss)
                elif w.objectName() == "aiMoreHeading":
                    w.setAutoFillBackground(True)
                    w.setStyleSheet(heading_ss)
                elif w.objectName() == "aiMoreCol":
                    w.setAutoFillBackground(True)
                else:
                    w.setAutoFillBackground(False)

        def _place_composer_icons(self) -> None:
            icons = getattr(self, "_composer_icons", None)
            host = getattr(self, "_composer", None)
            if icons is None or host is None:
                return
            icons.adjustSize()
            margin = 6
            x = max(margin, host.width() - icons.width() - margin)
            y = max(margin, host.height() - icons.height() - margin)
            icons.move(x, y)
            icons.raise_()

        def eventFilter(self, obj, event):  # noqa: N802
            menu = getattr(self, "_more_menu", None)
            if menu is not None and obj is menu and event.type() == QEvent.Type.Hide:
                self._more_reclick_guard = True
                QTimer.singleShot(0, self._clear_more_reclick_guard)
            if obj is getattr(self, "_composer", None) and event.type() == QEvent.Type.Resize:
                self._place_composer_icons()
            inp = getattr(self, "_input", None)
            if inp is not None and obj is inp and event.type() == QEvent.Type.KeyPress:
                key = event.key()
                mods = event.modifiers()
                if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter) and (
                    mods & (Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.MetaModifier)
                ):
                    self.send_current()
                    return True
            log = getattr(self, "_log", None)
            if (
                log is not None
                and obj is log.viewport()
                and event.type() == QEvent.Type.MouseButtonPress
                and event.button() == Qt.MouseButton.LeftButton
            ):
                pos = event.position().toPoint() if hasattr(event, "position") else event.pos()
                if self._try_mermaid_node_click(pos):
                    return True
            return QWidget.eventFilter(self, obj, event)

        def _try_mermaid_node_click(self, view_pos) -> bool:
            href = self._log.anchorAt(view_pos) or ""
            m = re.search(
                r"btfmermaid:(?://)?zoom[/:]([^?\s#]+)",
                href,
                re.IGNORECASE,
            )
            if not m:
                return False
            src = decode_mermaid_zoom_token(urllib.parse.unquote(m.group(1)))
            if not src:
                return False
            local = self._mermaid_img_local_pos(view_pos)
            if local is None:
                return False
            hit = hit_test_mermaid(src, local[0], local[1])
            if not hit:
                return False
            kind, value = hit
            if kind == "jump":
                self._on_jump_link(QUrl(btf_jump_href(value)))
            else:
                self._on_jump_link(QUrl(btf_highlight_href(value)))
            return True

        def _mermaid_img_local_pos(self, view_pos) -> Optional[Tuple[float, float]]:
            log = self._log
            cur = log.cursorForPosition(view_pos)
            block = cur.block()
            br = log.document().documentLayout().blockBoundingRect(block)
            it = block.begin()
            img_rect = None
            while not it.atEnd():
                frag = it.fragment()
                fmt = frag.charFormat()
                if fmt.isImageFormat():
                    rel = frag.position() - block.position()
                    tl = block.layout()
                    imgf = fmt.toImageFormat()
                    w = float(imgf.width() or 0)
                    h = float(imgf.height() or 0)
                    if w > 0 and h > 0 and tl is not None:
                        for li in range(tl.lineCount()):
                            line = tl.lineAt(li)
                            if line.textStart() <= rel < line.textStart() + max(line.textLength(), 1):
                                x1 = _qtextline_cursor_x(line, rel)
                                img_rect = QRectF(
                                    br.x() + line.x() + x1,
                                    br.y() + line.y(),
                                    w,
                                    h,
                                )
                                break
                    if img_rect is not None:
                        break
                it += 1
            if img_rect is None:
                return None
            doc_x = view_pos.x() + log.horizontalScrollBar().value()
            doc_y = view_pos.y() + log.verticalScrollBar().value()
            if not img_rect.contains(doc_x, doc_y):
                if img_rect.contains(float(view_pos.x()), float(view_pos.y())):
                    return (
                        float(view_pos.x()) - img_rect.x(),
                        float(view_pos.y()) - img_rect.y(),
                    )
                return None
            return doc_x - img_rect.x(), doc_y - img_rect.y()

        def _active_ai_settings(self) -> Dict[str, str]:
            return resolve_ai_settings(self._settings_dict())

        def _refresh_auth_chip(self) -> None:
            active = self._active_ai_settings()
            _id, label, _b, _m = ai_preset_info(active["preset"])
            st = ai_auth_status(
                auth_mode=active.get("auth_mode", ""),
                api_key=active.get("api_key", ""),
                base_url=active.get("base_url", ""),
                preset_id=active["preset"],
            )
            self._auth_chip.setText(f"{label} · {st['label']}")
            cfg = self._settings_dict()
            priv = classify_trace_privacy(
                endpoint_is_local=is_local_ai_host(active.get("base_url", "")),
                redact_task_names=str(cfg.get("redact_task_names", "")).lower()
                in ("1", "true", "yes", "on"),
                sensitive=str(cfg.get("trace_sensitive", "")).lower()
                in ("1", "true", "yes", "on"),
            )
            self._privacy_chip.setText(format_privacy_chip(priv))
            self._privacy_chip.setToolTip(qt_wrap_tooltip(str(priv.get("note") or "")))
            needs = bool(st["needs_auth"]) or bool(getattr(self, "_auth_forced", False))
            self._auth_cta.setVisible(needs)
            url = ai_preset_signin_url(active["preset"], active.get("base_url", ""))
            self._auth_cta_signin.setVisible(
                st["mode"] == AI_AUTH_BROWSER or bool(url)
            )
            self._auth_cta_signin.setText(ai_preset_signin_label(active["preset"]))

        def _on_auth_chip(self) -> None:
            self._open_settings()

        def _mark_cost_start(self) -> None:
            self._cost_started = time.monotonic()

        def _flash_main_status(self, msg: str) -> None:
            short = (msg or "").split("\n", 1)[0][:200]
            if not short:
                return
            wnd = self.window()
            getter = getattr(wnd, "statusBar", None)
            if not callable(getter):
                return
            try:
                getter().showMessage(f"AI: {short}", 6000)
            except RuntimeError:
                pass

        def _set_status(self, msg: str, *, error: bool = False) -> None:
            self._status.setText(str(msg or ""))
            self._status.setStyleSheet(
                "color:#e07070;font-size:11px;" if error
                else "color:#999;font-size:11px;"
            )
            self._refresh_usage()
            if error:
                self._flash_main_status(msg)

        def _refresh_usage(self) -> None:
            bar = getattr(self, "_usage", None)
            if bar is None:
                return
            bar.setText(format_cost_status(self._cost_meter))
            bar.setToolTip(qt_wrap_tooltip(format_cost_meter(self._cost_meter)))

        def _restore_ai_split(self) -> None:
            split = getattr(self, "_split", None)
            if split is None:
                return
            raw = ""
            if get_settings:
                try:
                    raw = str((get_settings() or {}).get("split_bottom") or "")
                except Exception:
                    raw = ""
            bottom = clamp_ai_split_bottom(raw)
            total = max(split.height(), 1)
            top = max(80, total - bottom)
            self._split_ready = False
            split.setSizes([top, bottom])
            self._split_ready = True

        def _on_ai_split_moved(self, _pos: int, _index: int) -> None:
            if not getattr(self, "_split_ready", False):
                return
            sizes = self._split.sizes() if getattr(self, "_split", None) else []
            if len(sizes) < 2 or not on_save_settings:
                return
            on_save_settings({"split_bottom": str(clamp_ai_split_bottom(sizes[1]))})

        def _record_turn_usage(self, turn: dict, calls: Sequence[Any]) -> None:
            usage = turn.get("usage") if isinstance(turn, dict) else {}
            if not isinstance(usage, dict):
                usage = {}
            names = [
                str(c.get("name") or "")
                for c in (calls or [])
                if isinstance(c, dict)
            ]
            elapsed = 0.0
            if self._cost_started:
                elapsed = max(0.0, time.monotonic() - float(self._cost_started))
            self._cost_meter = accumulate_cost(
                self._cost_meter,
                prompt_tokens=usage.get("prompt_tokens") or 0,
                completion_tokens=usage.get("completion_tokens") or 0,
                tool_calls=len(names),
                trace_queries=sum(1 for n in names if is_query_tool(n)),
                model_time_s=elapsed,
            )
            self._refresh_usage()

        def _open_signin_page(self) -> None:
            active = self._active_ai_settings()
            url = ai_preset_signin_url(active["preset"], active.get("base_url", ""))
            if url:
                QDesktopServices.openUrl(QUrl(url))
                self._set_status(
                    f"Opened {url}. Paste the key or token in Settings → AI.")
            else:
                self._set_status(
                    "This preset has no sign-in page. Paste a token in Settings → AI.")
            self._open_settings()

        def _open_settings(self) -> None:
            if on_open_settings:
                on_open_settings()

        def _choose_language(self) -> None:
            cfg = self._settings_dict()
            current = cfg.get("response_language", DEFAULT_AI_RESPONSE_LANGUAGE)
            dlg = _AiLanguageDialog(current, self)
            if dlg.exec() != QDialog.DialogCode.Accepted:
                return
            lang = dlg.selected_language()
            if on_save_settings:
                on_save_settings({"response_language": lang})
            self._set_status(f"Reply language: {lang}")
            self._refresh_localized_chrome(lang)

        def _refresh_localized_chrome(self, language: Optional[str] = None) -> None:
            """Re-render plan/evidence when reply language changes."""
            lang = (
                (language or self._reply_language()).strip()
                or DEFAULT_AI_RESPONSE_LANGUAGE
            )
            if self._investigation_plan:
                self._plan_view.setText(format_investigation_plan_status(
                    self._investigation_plan, lang))
            if self._evidence_payload:
                self._sync_evidence_log_entry(self._evidence_payload, lang)
            else:
                self._refresh_log()

        def _on_jump_link(self, url: QUrl) -> None:
            scheme = (url.scheme() or "").lower()
            if scheme in ("http", "https", "mailto"):
                QDesktopServices.openUrl(url)
                return
            if scheme == "btfmermaid":
                raw = url.toString()
                m = re.search(
                    r"btfmermaid:(?://)?zoom[/:]([^?\s#]+)",
                    raw,
                    re.IGNORECASE,
                )
                token = urllib.parse.unquote(m.group(1)) if m else ""
                src = decode_mermaid_zoom_token(token)
                if src:
                    self._open_mermaid_zoom(src)
                return
            if scheme == "btfaction":
                raw = url.toString()
                m = re.search(
                    r"btfaction:(?://)?(apply|skip|undo)[/:]([^?\s#]+)",
                    raw,
                    re.IGNORECASE,
                )
                if m:
                    self._on_tool_action(m.group(1).lower(), urllib.parse.unquote(m.group(2)))
                return
            if scheme == "btfhyp":
                action, hyp_id = parse_btf_hyp_href(url.toString())
                if action:
                    self._on_hypothesis_action(action, hyp_id)
                return
            if scheme == "btfscope":
                action, key = parse_btf_scope_href(url.toString())
                if action:
                    self._on_scope_action(action, key)
                return
            if scheme == "btfexp":
                action, key = parse_btf_exp_href(url.toString())
                if action:
                    self._on_experiment_action(action, key)
                return
            if scheme == "btftool":
                action, name = parse_btf_tool_href(url.toString())
                if action:
                    self._on_tool_why(action, name)
                return
            if scheme == "btfhighlight":
                raw = url.toString()
                name = parse_btf_highlight_href(raw)
                if not name:
                    try:
                        name = parse_btf_highlight_href(
                            bytes(url.toEncoded()).decode("ascii", "replace")
                        )
                    except Exception:
                        name = ""
                if on_highlight and name:
                    on_highlight(name)
                return
            if scheme == "btfrange":
                pair = parse_btf_range_href(url.toString())
                if pair and on_range:
                    on_range(pair[0], pair[1])
                return
            if not on_jump or scheme != "btfjump":
                return
            value = parse_btf_jump_href(url.toString())
            if value is None:
                return
            on_jump(value)

        def _open_mermaid_zoom(self, source: str) -> None:
            dlg = _MermaidZoomDialog(source, self, on_link=self._on_jump_link)
            dlg.exec()

        def _pending_batch_id(self) -> str:
            for bid, batch in reversed(list(self._pending_batches.items())):
                tools = batch.get("tools") or []
                if any(str(t.get("status") or "pending") == "pending" for t in tools if isinstance(t, dict)):
                    return str(bid)
            return ""

        def _applied_batch_id(self) -> str:
            for bid, batch in reversed(list(self._pending_batches.items())):
                tools = batch.get("tools") or []
                if any(str(t.get("status") or "") == "applied" for t in tools if isinstance(t, dict)):
                    return str(bid)
            return ""

        def _refresh_tool_bar(self) -> None:
            bar = getattr(self, "_tool_bar", None)
            if bar is None:
                return
            pending = self._pending_batch_id()
            applied = self._applied_batch_id()
            has_cards = any(ai_entry_tools(e) for e in self._entries)
            # In-log Apply/Skip/Undo cards are the primary chrome; keep this
            # bar only as a fallback when a batch exists without a card.
            show = bool(pending or applied) and not has_cards
            self._apply_tools_btn.setVisible(bool(pending))
            self._skip_tools_btn.setVisible(bool(pending))
            self._undo_tools_btn.setVisible(bool(applied) and not pending)
            bar.setVisible(show)

        def _apply_pending_tools(self) -> None:
            bid = self._pending_batch_id()
            if bid:
                self._on_tool_action("apply", bid)

        def _skip_pending_tools(self) -> None:
            bid = self._pending_batch_id()
            if bid:
                self._on_tool_action("skip", bid)

        def _undo_last_tools(self) -> None:
            bid = self._applied_batch_id()
            if bid:
                self._on_tool_action("undo", bid)

        def _reply_language(self) -> str:
            return str(self._settings_dict().get(
                "response_language", DEFAULT_AI_RESPONSE_LANGUAGE))

        def _refresh_log(self) -> None:
            """Rebuild the log from entries. QTextBrowser.append() merges HTML blocks."""
            if not self._entries:
                self._log.clear()
                self._refresh_tool_bar()
                return
            self._log.document().setDefaultStyleSheet(_ai_log_style(
                bool(getattr(self, "_is_dark", True))))
            lang = self._reply_language()
            self._log.setHtml(_ai_log_document_html(
                self._entries, lang,
                is_dark=bool(getattr(self, "_is_dark", True)),
            ))
            bar = self._log.verticalScrollBar()
            bar.setValue(bar.maximum())
            self._refresh_tool_bar()

        def _append(self, role: str, text: str, **extra: Any) -> None:
            if extra:
                entry: Any = {"role": role, "text": text}
                entry.update(extra)
                self._entries.append(entry)
            else:
                self._entries.append((role, text))
            self._refresh_log()

        def clear_conversation(self) -> None:
            """Clear the conversation log (also stops an in-flight query)."""
            if self._busy:
                self.stop_query()
            self._entries.clear()
            self._chat_messages = []
            self._pending_batches.clear()
            self._tool_round = 0
            self._log.clear()
            self._cost_meter = empty_cost_meter()
            self._set_status("")
            self._refresh_usage()
            self._clear_evidence_log_entry()
            self._interpreted_query = None
            self._refresh_tool_bar()

        def _show_log_menu(self, pos) -> None:
            menu = self._log.createStandardContextMenu(pos)
            menu.addSeparator()
            copy_all = menu.addAction("Copy conversation")
            copy_all.setEnabled(bool(self._entries))
            copy_all.triggered.connect(self.copy_conversation)
            menu.addSeparator()
            has_log = bool(self._entries)
            save_md = menu.addAction("Save As Markdown…")
            save_md.setEnabled(has_log)
            save_md.triggered.connect(lambda: self.save_conversation_as("md"))
            save_txt = menu.addAction("Save As Text…")
            save_txt.setEnabled(has_log)
            save_txt.triggered.connect(lambda: self.save_conversation_as("txt"))
            save_html = menu.addAction("Save As HTML…")
            save_html.setEnabled(has_log)
            save_html.triggered.connect(lambda: self.save_conversation_as("html"))
            menu.exec(self._log.mapToGlobal(pos))

        def copy_conversation(self) -> None:
            """Copy the whole conversation to the clipboard as Markdown."""
            if not self._entries:
                return
            clip = QApplication.clipboard()
            if clip is None:
                self._set_status("Clipboard is not available.")
                return
            clip.setText(format_ai_conversation_markdown(
                self._entries, self._reply_language()))
            self._set_status("Copied to clipboard.")

        def save_conversation_as(self, preferred: str = "") -> None:
            """Write the conversation to Markdown, plain text or HTML."""
            if not self._entries:
                return
            kind = (preferred or "").lower()
            stamp = _ai_file_stamp()
            if kind == "txt":
                start = f"ai-conversation-{stamp}.txt"
                filters = "Text files (*.txt);;Markdown (*.md);;HTML (*.html);;All files (*)"
            elif kind in ("html", "htm"):
                start = f"ai-conversation-{stamp}.html"
                filters = "HTML (*.html);;Markdown (*.md);;Text files (*.txt);;All files (*)"
            else:
                start = f"ai-conversation-{stamp}.md"
                filters = "Markdown (*.md);;Text files (*.txt);;HTML (*.html);;All files (*)"
            path, selected = QFileDialog.getSaveFileName(
                self,
                "Save AI Conversation",
                start,
                filters,
            )
            if not path:
                return
            lower = path.lower()
            if not lower.endswith((".md", ".txt", ".html", ".htm")):
                ext = ".txt" if "Text" in selected else (
                    ".html" if "HTML" in selected else ".md")
                path += ext
                lower = path.lower()
            lang = self._reply_language()
            if lower.endswith((".html", ".htm")):
                data = format_ai_conversation_html(self._entries, lang)
            elif lower.endswith(".txt"):
                data = format_ai_conversation_text(self._entries, lang)
            else:
                data = format_ai_conversation_markdown(self._entries, lang)
            try:
                with open(path, "w", encoding="utf-8") as fh:
                    fh.write(data)
            except OSError as exc:
                QMessageBox.warning(
                    self, "Save failed", f"Could not write file:\n{exc}")
                return
            self._set_status(f"Saved conversation to {os.path.basename(path)}")

        def _collect_conversation_tools_run(self) -> List[str]:
            """Tool names successfully applied so far this session, in order."""
            out: List[str] = []
            for e in self._entries:
                for t in ai_entry_tools(e):
                    if isinstance(t, dict) and t.get("status") == "applied":
                        nm = str(t.get("name") or "")
                        if nm:
                            out.append(nm)
            return out

        def _collect_conversation_evidence_times(self) -> List[float]:
            """jump:TIME evidence timestamps cited across assistant replies."""
            out: List[float] = []
            for e in self._entries:
                if ai_entry_role(e) == "assistant":
                    out.extend(extract_jump_times(ai_entry_text(e)))
            return out

        def _export_investigation_package(
            self, args: Dict[str, Any], *, meta: Dict[str, str],
        ) -> Dict[str, Any]:
            """Build + save the JSON investigation replay package."""
            finding_id = str((args or {}).get("finding_id") or "").strip()
            conclusion = str((args or {}).get("conclusion") or "").strip()
            tools_run = [str(t) for t in ((args or {}).get("tools_run") or []) if t]
            evidence_times = [
                float(t) for t in ((args or {}).get("evidence_times") or [])
                if isinstance(t, (int, float))
            ]
            if not tools_run:
                tools_run = self._collect_conversation_tools_run()
            if not evidence_times:
                evidence_times = self._collect_conversation_evidence_times()
            if not conclusion:
                for e in reversed(self._entries):
                    if ai_entry_role(e) == "assistant":
                        text = ai_entry_text(e).strip()
                        if text:
                            conclusion = text[:2000]
                            break
            finding = {"id": finding_id, "title": finding_id} if finding_id else None
            package = build_investigation_package(
                trace_name=meta.get("file", ""),
                scope=meta.get("scope", ""),
                finding=finding,
                plan=self._investigation_plan,
                tools_run=tools_run,
                conclusion=conclusion,
                evidence_times=evidence_times,
                timestamp=datetime.datetime.now().isoformat(),
            )
            data = json.dumps(package, ensure_ascii=True, indent=2)
            start = f"ai-investigation-{_ai_file_stamp()}.json"
            path, _selected = QFileDialog.getSaveFileName(
                self, "Export Investigation", start, "JSON (*.json);;All files (*)")
            if not path:
                return tool_result_payload(False, "Export cancelled")
            if not path.lower().endswith(".json"):
                path += ".json"
            try:
                with open(path, "w", encoding="utf-8") as fh:
                    fh.write(data)
            except OSError as exc:
                return tool_result_payload(False, f"Could not write file: {exc}")
            base = os.path.basename(path)
            self._set_status(f"Saved investigation to {base}")
            return tool_result_payload(
                True, f"Saved investigation package to {base}", path=path)

        def _export_ai_report(
            self, name: str, args: Dict[str, Any],
        ) -> Dict[str, Any]:
            """Write findings + GUI state + conversation (export_report /
            export_investigation tools)."""
            name = str(name or AI_TOOL_EXPORT_REPORT)
            args = args or {}
            fmt = str(args.get("format") or "html").strip().lower()
            if fmt not in ("html", "csv", "json"):
                fmt = "html"
            gui: Dict[str, Any] = {}
            if on_gui_state:
                try:
                    gui = dict(on_gui_state() or {})
                except Exception as exc:
                    return tool_result_payload(False, f"GUI state error: {exc}")
            findings = str(gui.pop("findings", "") or "")
            if not findings and get_context:
                try:
                    findings = str((get_context() or {}).get("findings_text") or "")
                except Exception:
                    findings = ""
            meta = {
                "file": gui.pop("file", "") or "",
                "span": gui.pop("span", "") or "",
                "cores": gui.pop("cores", "") or "",
                "scope": gui.pop("scope", "") or "",
            }
            annotations = (
                gui.get("annotations") if isinstance(gui.get("annotations"), list) else []
            )
            if name == AI_TOOL_EXPORT_INVESTIGATION or fmt == "json":
                return self._export_investigation_package(args, meta=meta)
            stamp = _ai_file_stamp()
            if fmt == "csv":
                start = f"ai-report-{stamp}.csv"
                filters = "CSV (*.csv);;All files (*)"
                data = build_ai_report_csv(
                    meta=meta,
                    gui=gui,
                    findings=findings,
                    annotations=annotations,
                    conversation=format_ai_conversation_text(self._entries),
                )
            else:
                start = f"ai-report-{stamp}.html"
                filters = "HTML (*.html);;All files (*)"
                conv_html = format_ai_conversation_html_body(self._entries)
                data = build_ai_report_html(
                    meta=meta,
                    gui=gui,
                    findings=findings,
                    annotations=annotations,
                    conversation_html=conv_html,
                )
            path, _selected = QFileDialog.getSaveFileName(
                self, "Export AI Report", start, filters)
            if not path:
                return tool_result_payload(False, "Export cancelled")
            lower = path.lower()
            if fmt == "csv" and not lower.endswith(".csv"):
                path += ".csv"
            elif fmt == "html" and not lower.endswith((".html", ".htm")):
                path += ".html"
            try:
                with open(path, "w", encoding="utf-8") as fh:
                    fh.write(data)
            except OSError as exc:
                return tool_result_payload(False, f"Could not write file: {exc}")
            base = os.path.basename(path)
            self._set_status(f"Saved report to {base}")
            return tool_result_payload(True, f"Saved {fmt} report to {base}", path=path)

        def stop_query(self) -> None:
            """Abort the current AI request if one is running."""
            if not self._busy:
                return
            self._set_status("Stopping…")
            worker = self._worker
            if worker is not None:
                worker.cancel()

        def _ai_is_enabled(self) -> bool:
            cfg = self._settings_dict()
            return str(cfg.get("enabled", "true")).lower() not in (
                "0", "false", "no", "off",
            )

        def _on_composer_action(self) -> None:
            if self._busy:
                self.stop_query()
            else:
                self.send_current()

        def _refresh_send_btn(self) -> None:
            if self._busy:
                self._send_btn.setIcon(self._icon_stop)
                self._send_btn.setToolTip("Stop the current query")
                self._send_btn.setEnabled(True)
                return
            self._send_btn.setIcon(self._icon_send)
            self._send_btn.setToolTip("Send the question (Ctrl/Cmd+Enter)")
            self._send_btn.setEnabled(
                self._ai_is_enabled()
                and bool(self._input.toPlainText().strip())
            )

        def _set_busy(self, busy: bool) -> None:
            self._busy = busy
            enabled = self._ai_is_enabled()
            self._refresh_send_btn()
            self._input.setReadOnly(busy or (not enabled))
            live = (not busy) and enabled
            for btn in self._template_btns:
                btn.setEnabled(live)
            for btn in getattr(self, "_mode_btns", []):
                btn.setEnabled(live)
            for act in self._template_actions.values():
                act.setEnabled(live)
            for act in getattr(self, "_investigation_template_actions", {}).values():
                act.setEnabled(live)
            save_act = getattr(self, "_save_investigation_template_action", None)
            if save_act is not None:
                save_act.setEnabled(not busy)
            know_act = getattr(self, "_save_knowledge_action", None)
            if know_act is not None:
                know_act.setEnabled(not busy)
            self.refresh_template_availability()
            if (not enabled) and (not busy):
                self._set_status("AI is disabled in Settings → AI.")

        def refresh_enabled_state(self) -> None:
            """Re-apply enable/disable after Settings → AI changes."""
            self._set_busy(self._busy)
            self._refresh_auth_chip()

        def _loaded_tabs(self) -> List[Dict[str, Any]]:
            if not get_loaded_tabs:
                return []
            try:
                tabs = list(get_loaded_tabs() or [])
            except Exception:
                return []
            out: List[Dict[str, Any]] = []
            for t in tabs:
                if not isinstance(t, dict):
                    continue
                if t.get("index") is None:
                    continue
                out.append(t)
            return out

        def refresh_template_availability(self) -> None:
            """Enable Trace Compare only when 2+ loaded tabs exist; gray out
            SMP-only templates (Migration thrash, Core balance) for a
            single-core trace."""
            disabled_base = self._busy or not self._ai_is_enabled()

            for _tid, btn in self._smp_only_btns.items():
                if disabled_base:
                    btn.setEnabled(False)
                    continue
                if self._trace_is_multi_core():
                    prompt = next(
                        (p for tid, _lab, p in AI_TEMPLATE_QUESTIONS if tid == _tid), ""
                    )
                    btn.setEnabled(True)
                    btn.setToolTip(qt_wrap_tooltip(prompt))
                else:
                    btn.setEnabled(False)
                    btn.setToolTip(qt_wrap_tooltip(
                        "This trace has a single core — not applicable."
                    ))

            if self._compare_btn is None:
                return
            n = len(self._loaded_tabs())
            prompt = next(
                (p for tid, _lab, p in AI_TEMPLATE_QUESTIONS if tid == AI_COMPARE_TEMPLATE_ID),
                "Trace Compare",
            )
            if disabled_base:
                self._compare_btn.setEnabled(False)
                return
            if n < 2:
                self._compare_btn.setEnabled(False)
                self._compare_btn.setToolTip(qt_wrap_tooltip(
                    "Open at least two BTF tabs to use Trace Compare."
                ))
            else:
                self._compare_btn.setEnabled(True)
                self._compare_btn.setToolTip(qt_wrap_tooltip(prompt))

        def _trace_is_multi_core(self) -> bool:
            if not get_context:
                return True
            try:
                cores = int((get_context() or {}).get("cores") or 0)
            except Exception:
                return True
            return cores == 0 or cores >= 2

        def showEvent(self, event) -> None:  # noqa: N802
            super().showEvent(event)
            self.refresh_enabled_state()

        def query_template(
            self, template_id: str, *, finding_id: str = "", extra: str = "",
        ) -> None:
            """Run a built-in AI template by id (toolbar Analysis / inspector)."""
            prompt = next(
                (p for tid, _lab, p in AI_TEMPLATE_QUESTIONS if tid == template_id),
                "",
            )
            if prompt:
                fid = str(finding_id or "").strip()
                if fid:
                    prompt = f"{prompt}\n\nfinding_id={fid}"
                extra = str(extra or "").strip()
                if extra:
                    prompt = f"{prompt}\n\n{extra}"
                if template_id == "explain_region" and get_context:
                    try:
                        cursors = (get_context() or {}).get("cursors") or []
                    except Exception:
                        cursors = []
                    prompt = append_explain_region_bounds(prompt, cursors)
                self._use_template(template_id, prompt)

        def ask_event(self, event: Dict[str, Any]) -> None:
            """Timeline context menu → Ask AI about this event."""
            prompt = compose_ask_event_prompt(event)
            self._use_template("ask_event", prompt)

        def ask(self, prompt: str) -> None:
            """Generic programmatic ask (composed prompt, no fixed template)."""
            prompt = str(prompt or "").strip()
            if not prompt:
                return
            self._use_template("", prompt)

        def query_analysis_findings(self) -> None:
            """Run the Analysis Findings template (toolbar Analysis → Query with AI)."""
            self.query_template("findings")

        def query_migration_thrash(self) -> None:
            """Run the Migration thrash template (inspector → Query with AI)."""
            self.query_template("migrations")

        def query_trace_compare(self, idx_a: int, idx_b: int) -> None:
            """Run the Trace Compare template for two already-chosen tabs."""
            prompt = next(
                (p for tid, _lab, p in AI_TEMPLATE_QUESTIONS
                 if tid == AI_COMPARE_TEMPLATE_ID),
                "",
            )
            if prompt:
                self._run_compare_template(prompt, idx_a=idx_a, idx_b=idx_b)

        def query_validate_experiment(self, idx_a: int, idx_b: int) -> None:
            """Ask the model to call validate_experiment for two chosen tabs."""
            self._skip_interpret = True
            self._active_template_id = ""
            self._run_compare_template(
                VALIDATE_EXPERIMENT_PROMPT, idx_a=idx_a, idx_b=idx_b)

        def _use_template(self, template_id: str, prompt: str) -> None:
            if self._busy:
                return
            self._skip_interpret = True
            self._active_template_id = str(template_id or "")
            if is_agent_template(template_id):
                self._set_investigation_plan(default_investigation_plan(
                    next((p for tid, _l, p in AI_TEMPLATE_QUESTIONS if tid == template_id), "")[:80]
                    or "Investigate the main performance problem"
                ))
            else:
                self._clear_investigation_plan()
            if template_id == AI_COMPARE_TEMPLATE_ID:
                self._run_compare_template(prompt)
                return
            self._input.setPlainText(prompt)
            self.send_current()

        def _hide_more_menu(self) -> None:
            menu = getattr(self, "_more_menu", None)
            if menu is not None and menu.isVisible():
                menu.hide()

        def _clear_more_reclick_guard(self) -> None:
            self._more_reclick_guard = False

        def _toggle_more_menu(self) -> None:
            if getattr(self, "_more_reclick_guard", False):
                return
            menu = getattr(self, "_more_menu", None)
            if menu is None:
                return
            if menu.isVisible():
                menu.hide()
                return
            self._paint_more_menu()
            self._place_more_menu()
            menu.show()

        def _place_more_menu(self) -> None:
            """Size to full 2-column content (web overlay is not a scroller)."""
            btn = getattr(self, "_more_btn", None)
            menu = getattr(self, "_more_menu", None)
            if btn is None or menu is None:
                return
            menu.setMinimumHeight(0)
            menu.setMaximumHeight(16777215)
            menu.adjustSize()
            hint = menu.sizeHint()
            width = max(360, int(hint.width()))
            height = max(1, int(hint.height()))
            gap = 4
            br = btn.rect()
            top_left = btn.mapToGlobal(br.topLeft())
            bottom_right = btn.mapToGlobal(br.bottomRight())
            screen = QApplication.primaryScreen().availableGeometry()
            win = btn.window()
            if win is not None and win.screen() is not None:
                screen = win.screen().availableGeometry()
            space_below = screen.bottom() - bottom_right.y()
            space_above = top_left.y() - screen.top()
            x = bottom_right.x() - width
            x = max(screen.left() + 8, min(x, screen.right() - width - 8))
            if space_below >= height + gap:
                y = bottom_right.y() + gap
            elif space_above >= height + gap:
                y = top_left.y() - gap - height
            elif space_above >= space_below:
                y = max(screen.top() + 8, top_left.y() - gap - height)
            else:
                y = bottom_right.y() + gap
                if y + height > screen.bottom() - 8:
                    y = max(screen.top() + 8, screen.bottom() - 8 - height)
            menu.resize(width, height)
            menu.move(x, y)

        def _on_more_template(self, template_id: str, prompt: str) -> None:
            self._hide_more_menu()
            self._use_template(template_id, prompt)

        def _user_investigation_templates(self) -> List[Dict[str, Any]]:
            raw = ""
            if get_settings:
                try:
                    raw = str(
                        (get_settings() or {}).get("user_investigation_templates")
                        or ""
                    )
                except Exception:
                    raw = ""
            return parse_user_investigation_templates(raw)

        def _all_investigation_templates(self) -> List[Dict[str, Any]]:
            return list(builtin_investigation_templates()) + self._user_investigation_templates()

        def _rebuild_investigation_menu(self) -> None:
            col = getattr(self, "_investigation_col", None)
            if col is None:
                return
            lay = col.layout()
            _clear_layout(lay)
            lay.addWidget(_ai_more_heading("Investigations"))
            self._investigation_template_actions = {}
            live = (not self._busy) and self._ai_is_enabled()
            for tpl in self._all_investigation_templates():
                label = str(tpl.get("label") or tpl.get("id") or "").strip()
                if not label:
                    continue
                act = _ai_more_item(
                    label,
                    investigation_template_prompt(tpl),
                )
                act.setEnabled(live)
                act.clicked.connect(
                    lambda _=False, t=dict(tpl): self._on_more_investigation(t)
                )
                lay.addWidget(act)
                self._investigation_template_actions[str(tpl.get("id") or "")] = act
            save_act = _ai_more_item(
                "Save as template\u2026",
                "Save the current investigation steps as a reusable template",
            )
            save_act.setEnabled(not self._busy)
            save_act.clicked.connect(self._on_more_save_template)
            self._save_investigation_template_action = save_act
            lay.addWidget(save_act)
            lay.addWidget(_ai_more_heading("Knowledge"))
            know_act = _ai_more_item(
                "Save current finding\u2026",
                "Store this finding as local historical knowledge",
            )
            know_act.setEnabled(not self._busy)
            know_act.clicked.connect(self._on_more_save_knowledge)
            self._save_knowledge_action = know_act
            lay.addWidget(know_act)
            lay.addStretch(1)
            self._paint_more_menu()

        def _on_more_investigation(self, tpl: Dict[str, Any]) -> None:
            self._hide_more_menu()
            self._run_investigation_template(tpl)

        def _on_more_save_template(self) -> None:
            self._hide_more_menu()
            self._save_investigation_template()

        def _on_more_save_knowledge(self) -> None:
            self._hide_more_menu()
            self._save_user_knowledge()

        def _save_investigation_template(self) -> None:
            steps: List[str] = []
            plan = self._investigation_plan if isinstance(self._investigation_plan, dict) else {}
            for s in plan.get("steps") or []:
                if isinstance(s, dict) and s.get("id"):
                    steps.append(str(s.get("id")))
                elif s:
                    steps.append(str(s))
            if not steps:
                case = (self._evidence_payload or {}).get("investigation_case") or {}
                steps = [str(t) for t in (case.get("tools_executed") or []) if t]
            name, ok = QInputDialog.getText(
                self, "Save investigation template",
                "Template name:",
                text="My Investigation",
            )
            if not ok:
                return
            tpl = new_user_investigation_template(name, steps)
            items = self._user_investigation_templates()
            items = [it for it in items if it.get("id") != tpl["id"]]
            items.append(tpl)
            if on_save_settings:
                on_save_settings({
                    "user_investigation_templates": dump_user_investigation_templates(items),
                })
            self._rebuild_investigation_menu()

        def _run_investigation_mode(self, mode: str) -> None:
            if self._busy:
                return
            plan = investigation_mode_plan(mode)
            label = INVESTIGATION_MODE_LABELS.get(plan["mode"], str(mode))
            prompt = investigation_mode_prompt(plan["mode"])
            steps = [
                {"id": str(s), "label": str(s), "status": "pending"}
                for s in (plan.get("tools") or []) if s
            ]
            self._active_template_id = str(plan.get("template") or plan["mode"])
            if steps:
                self._set_investigation_plan({"goal": label, "steps": steps})
            else:
                self._clear_investigation_plan()
            self._skip_interpret = True
            self._input.setPlainText(prompt)
            self.send_current()

        def _on_hypothesis_action(self, action: str, hyp_id: str) -> None:
            act = str(action or "").strip().lower()
            hid = str(hyp_id or "").strip()
            payload = dict(self._evidence_payload or {})
            hyps = list(
                payload.get("hypotheses_managed")
                or payload.get("hypotheses")
                or []
            )
            if act in ("supported", "rejected", "need_evidence", "possible"):
                updated = set_hypothesis_status(hyps, hid, act)
                payload["hypotheses_managed"] = updated
                payload["hypotheses"] = updated
                case = dict(payload.get("investigation_case") or {})
                if case:
                    case["hypotheses"] = updated
                    payload["investigation_case"] = case
                self._evidence_payload = payload
                self._sync_evidence_log_entry(payload)
                return
            if act == "compare":
                ranked = compare_hypotheses(hyps)
                leader = ranked.get("leader") or {}
                title = str(leader.get("hypothesis") or "Compare hypotheses")
                payload["hypotheses_managed"] = ranked.get("ranked") or hyps
                payload["conclusion"] = f"Leader: {title}" if title else "Compare hypotheses"
                self._evidence_payload = payload
                self._sync_evidence_log_entry(payload)
                return
            if act == "test":
                name = hid
                for h in hyps:
                    if isinstance(h, dict) and str(h.get("id") or "") == hid:
                        name = str(h.get("hypothesis") or hid)
                        break
                prompt = (
                    f"Test hypothesis {name!r} (id={hid}). "
                    "Call investigate then correlate_events, find_critical_path, "
                    "build_task_dependency_graph, analyze_temporal_causality, "
                    "rank_root_causes, and challenge_conclusion. "
                    f"Then manage_hypotheses(hypothesis_id={hid}, "
                    "status=supported|rejected|need_evidence). "
                    "Finish with a verdict, jump:TIME evidence, and one next check."
                )
                self._use_template("investigate", prompt)

        def _on_scope_action(self, action: str, key: str) -> None:
            act = str(action or "").strip().lower()
            interpreted = dict(
                getattr(self, "_interpreted_query", None)
                or (self._evidence_payload or {}).get("interpreted")
                or {}
            )
            if act == "toggle":
                interpreted = toggle_interpreted_scope(interpreted, key)
                self._interpreted_query = interpreted
                payload = dict(self._evidence_payload or {})
                payload["interpreted"] = interpreted
                scopes = [str(s) for s in (interpreted.get("scope") or []) if s]
                mode = str(interpreted.get("mode") or interpreted.get("kind") or "")
                payload["subtitle"] = (
                    f"{mode}: {', '.join(scopes)}" if mode and scopes
                    else ", ".join(scopes) or mode
                )
                self._evidence_payload = payload
                self._sync_evidence_log_entry(payload)
                return
            if act == "edit":
                q = str(interpreted.get("interpreted_question") or "").strip()
                text, ok = QInputDialog.getMultiLineText(
                    self, "Edit scope", "Interpreted question:", q,
                )
                if ok and str(text or "").strip():
                    interpreted["interpreted_question"] = str(text).strip()
                    self._interpreted_query = interpreted
                    payload = dict(self._evidence_payload or {})
                    payload["interpreted"] = interpreted
                    payload["conclusion"] = interpreted["interpreted_question"]
                    self._evidence_payload = payload
                    self._sync_evidence_log_entry(payload)
                return
            if act == "run":
                self._use_template("investigate", interpreted_run_prompt(interpreted))

        def _on_experiment_action(self, action: str, _key: str) -> None:
            if str(action or "").strip().lower() != "save":
                return
            self._save_user_knowledge()

        def _on_tool_why(self, action: str, name: str) -> None:
            if str(action or "").strip().lower() != "why":
                return
            want = str(name or "").strip()
            reasons = list((self._evidence_payload or {}).get("tool_reasons") or [])
            why = ""
            for r in reasons:
                if isinstance(r, dict) and str(r.get("tool") or "") == want:
                    why = str(r.get("reason") or "")
                    break
            self._set_status(
                f"{want}: {why}" if why else f"{want}: no recorded reason"
            )

        def _user_historical_knowledge(self) -> List[Dict[str, Any]]:
            raw = ""
            if get_settings:
                try:
                    raw = str(
                        (get_settings() or {}).get("user_historical_knowledge") or ""
                    )
                except Exception:
                    raw = ""
            return parse_user_historical_knowledge(raw)

        def _save_user_knowledge(self) -> None:
            payload = dict(self._evidence_payload or {})
            finding = payload.get("finding") if isinstance(payload.get("finding"), dict) else {}
            if not finding:
                case = payload.get("investigation_case") or {}
                items = case.get("suspected_findings") or []
                if items and isinstance(items[0], dict):
                    finding = items[0]
            hk = payload.get("historical_knowledge") if isinstance(
                payload.get("historical_knowledge"), dict) else {}
            extras = {
                "issue": str(
                    payload.get("conclusion") or finding.get("title") or ""
                ),
                "fix": str(hk.get("known_fix") or ""),
                "build": str(hk.get("last_occurrence") or ""),
                "task": str(finding.get("task") or hk.get("task") or ""),
                "metrics": dict(hk.get("current") or hk.get("typical") or {}),
            }
            for key in ("migrations", "migration_rate", "blocking", "wcet"):
                if finding.get(key) is not None:
                    extras[key] = finding.get(key)
            entry = new_user_historical_entry(finding, extras)
            name, ok = QInputDialog.getText(
                self, "Save to knowledge",
                "Issue label:",
                text=str(entry.get("issue") or "Saved finding"),
            )
            if not ok:
                return
            entry["issue"] = str(name or entry["issue"]).strip() or entry["issue"]
            items = self._user_historical_knowledge()
            items = [
                it for it in items
                if not (
                    it.get("task") == entry.get("task")
                    and it.get("issue") == entry.get("issue")
                )
            ]
            items.append(entry)
            if on_save_settings:
                on_save_settings({
                    "user_historical_knowledge": dump_user_historical_knowledge(items),
                })
            self._set_status(f"Saved knowledge “{entry['issue']}”.")

        def _run_investigation_template(self, template: dict) -> None:
            if self._busy:
                return
            tpl = template if isinstance(template, dict) else {}
            prompt = investigation_template_prompt(tpl)
            steps = [
                {"id": str(s), "label": str(s), "status": "pending"}
                for s in (tpl.get("steps") or []) if s
            ]
            self._active_template_id = str(tpl.get("id") or "")
            if steps:
                self._set_investigation_plan({
                    "goal": str(tpl.get("label") or "Investigation"),
                    "steps": steps,
                })
            else:
                self._clear_investigation_plan()
            self._skip_interpret = True
            self._input.setPlainText(prompt)
            self.send_current()

        def _set_investigation_plan(self, plan: Optional[Dict[str, Any]]) -> None:
            self._investigation_plan = plan
            if not plan:
                self._clear_investigation_plan()
                return
            self._plan_view.setText(format_investigation_plan_status(
                plan, self._reply_language()))
            self._plan_host.show()

        def _clear_investigation_plan(self) -> None:
            self._investigation_plan = None
            self._plan_host.hide()
            self._plan_view.clear()

        def _sync_evidence_log_entry(
            self, data: dict, language: Optional[str] = None,
        ) -> None:
            """Structured evidence at the end of the log (exportable; no separate panel)."""
            lang = (
                (language or self._reply_language()).strip()
                or DEFAULT_AI_RESPONSE_LANGUAGE
            )
            text = format_evidence_panel_markdown(data, lang)
            if not text:
                return
            self._entries = [
                e for e in self._entries if ai_entry_role(e) != "evidence"
            ]
            self._append("evidence", text)

        def _pin_evidence_log_entry(self) -> None:
            """Keep evidence below the latest assistant reply."""
            if self._evidence_payload:
                self._sync_evidence_log_entry(self._evidence_payload)

        def _attach_response_validation(self, text: str) -> None:
            """Flag invented tasks / out-of-scope jump:TIME after the final reply."""
            src = str(text or "").strip()
            if not src:
                return
            ctx = {}
            if get_context:
                try:
                    ctx = normalize_ai_context(get_context() or {})
                except Exception:
                    ctx = {}
            bounds = cursor_region_bounds(ctx.get("cursors"))
            catalog = build_validation_catalog(
                findings_text=str(ctx.get("findings_text") or ""),
                evidence=(self._evidence_payload or {}).get("evidence"),
                cursor_lo=bounds[0] if bounds else None,
                cursor_hi=bounds[1] if bounds else None,
            )
            report = validate_ai_response(
                src,
                known_tasks=catalog.get("tasks"),
                known_times=catalog.get("times"),
                cursor_lo=catalog.get("cursor_lo"),
                cursor_hi=catalog.get("cursor_hi"),
            )
            payload = dict(self._evidence_payload or {})
            payload["validation"] = report
            payload["cost"] = format_cost_meter(self._cost_meter)
            if not payload.get("conclusion") and not payload.get("evidence"):
                payload["conclusion"] = payload.get("conclusion") or ""
            self._evidence_payload = payload

        def _update_evidence_from_tool_result(
            self, name: str, res: Dict[str, Any],
        ) -> None:
            payload = extract_evidence_panel_payload(name, res)
            if not payload:
                return
            prev = dict(self._evidence_payload or {})
            prev_case = prev.get("investigation_case")
            if prev_case:
                case = update_case_from_tool(prev_case, name, res)
                payload["investigation_case"] = case
                payload["tool_reasons"] = case.get("tool_reasons") or []
                payload["confidence_evolution"] = format_confidence_evolution(
                    case.get("confidence_history"))
            if prev.get("validation") and "validation" not in payload:
                payload["validation"] = prev["validation"]
            if prev.get("cost") and "cost" not in payload:
                payload["cost"] = prev["cost"]
            if payload.get("interpreted"):
                self._interpreted_query = dict(payload["interpreted"])
            elif prev.get("interpreted") and "interpreted" not in payload:
                payload["interpreted"] = prev["interpreted"]
            if payload.get("experiment"):
                hyps = list(
                    payload.get("hypotheses_managed")
                    or payload.get("hypotheses")
                    or prev.get("hypotheses_managed")
                    or prev.get("hypotheses")
                    or []
                )
                updated = apply_experiment_to_hypotheses(hyps, payload["experiment"])
                if updated:
                    payload["hypotheses_managed"] = updated
                    payload["hypotheses"] = updated
            finding = payload.get("finding") if isinstance(payload.get("finding"), dict) else None
            if finding:
                payload["historical_knowledge"] = historical_knowledge_for_finding(
                    finding,
                    current=finding,
                    user_catalog=self._user_historical_knowledge(),
                )
            self._evidence_payload = dict(payload)
            self._sync_evidence_log_entry(self._evidence_payload)

        def _clear_evidence_log_entry(self) -> None:
            self._evidence_payload = None
            kept = [e for e in self._entries if ai_entry_role(e) != "evidence"]
            if len(kept) != len(self._entries):
                self._entries = kept
                self._refresh_log()

        def _advance_investigation_plan(self, tool_names: Sequence[str]) -> None:
            if not self._investigation_plan:
                return
            self._set_investigation_plan(
                mark_plan_steps_from_tools(self._investigation_plan, tool_names)
            )

        def _finish_investigation_plan(self) -> None:
            if not self._investigation_plan:
                return
            self._set_investigation_plan(
                complete_investigation_plan(self._investigation_plan)
            )

        def _run_compare_template(
            self,
            prompt: str,
            idx_a: Optional[int] = None,
            idx_b: Optional[int] = None,
        ) -> None:
            tabs = self._loaded_tabs()
            if len(tabs) < 2:
                self._set_status("Open at least two BTF tabs to compare.")
                self.refresh_template_availability()
                return
            if idx_a is not None and idx_b is not None:
                idx_a, idx_b = int(idx_a), int(idx_b)
                if idx_a == idx_b:
                    self._set_status("Choose two different traces.")
                    return
            elif len(tabs) == 2:
                idx_a = int(tabs[0]["index"])
                idx_b = int(tabs[1]["index"])
            else:
                dlg = _AiComparePickDialog(tabs, self)
                if dlg.exec() != QDialog.DialogCode.Accepted:
                    return
                idx_a, idx_b = dlg.selected_indices()
                if idx_a == idx_b:
                    self._set_status("Choose two different traces.")
                    return
            if not build_compare_context:
                self._set_status("Trace Compare is not available.")
                return
            try:
                ctx = dict(build_compare_context(idx_a, idx_b) or {})
            except Exception as exc:
                self._set_status(f"Compare context error: {exc}")
                return
            ctx = normalize_ai_context(ctx)
            if not (ctx.get("findings_text") or "").strip():
                self._set_status("Could not build Trace Compare tables.")
                return
            self._input.clear()
            self._send_query(prompt, ctx)

        def _settings_dict(self) -> Dict[str, str]:
            if get_settings:
                return dict(get_settings() or {})
            return {
                "enabled": "true",
                "preset": DEFAULT_AI_PRESET,
                "response_language": DEFAULT_AI_RESPONSE_LANGUAGE,
            }

        def _on_ok(self, payload: str) -> None:
            self._auth_forced = False
            self._refresh_auth_chip()
            try:
                turn = json.loads(payload) if isinstance(payload, str) else {}
            except (TypeError, ValueError):
                turn = {"content": str(payload or ""), "tool_calls": []}
            if not isinstance(turn, dict):
                turn = {"content": str(payload or ""), "tool_calls": []}
            text = str(turn.get("content") or "").strip()
            calls = turn.get("tool_calls") if isinstance(turn.get("tool_calls"), list) else []
            self._record_turn_usage(turn, calls)
            if calls:
                self._chat_messages.append(
                    canonical_assistant_tool_message(text, calls)
                )
            elif text:
                self._chat_messages.append({"role": "assistant", "content": text})

            tools_norm: List[Dict[str, Any]] = []
            for c in calls:
                if not isinstance(c, dict):
                    continue
                name = str(c.get("name") or "")
                args = c.get("arguments") if isinstance(c.get("arguments"), dict) else {}
                ok_args, err = validate_tool_call(name, args)
                tools_norm.append({
                    "id": str(c.get("id") or f"call_{len(tools_norm)}"),
                    "name": name,
                    "arguments": ok_args or args,
                    "error": err,
                    "status": "pending",
                })
            if tools_norm:
                self._advance_investigation_plan(
                    [str(t.get("name") or "") for t in tools_norm]
                )

            auto = (
                parse_ai_auto_apply(self._settings_dict().get("auto_apply"))
                or tool_batch_auto_runs(tools_norm)
            )
            if tools_norm:
                self._batch_seq += 1
                batch_id = f"b{self._batch_seq}"
                self._pending_batches[batch_id] = {
                    "tools": tools_norm,
                    "entry_index": len(self._entries),
                }
                self._append("assistant", text, tools=tools_norm, batch_id=batch_id)
                if auto:
                    self._cleanup_worker()
                    self._apply_tool_batch(batch_id, skipped=False)
                    return
                self._set_status("Review GUI actions, then Apply or Skip.")
                self._cleanup_worker()
                return

            if text:
                self._append("assistant", text)
            self._finish_investigation_plan()
            self._attach_response_validation(text)
            self._pin_evidence_log_entry()
            jumps = extract_jump_times(text)
            if jumps:
                token = _JUMP_RE.search(text or "")
                label = token.group(1) if token else f"{jumps[0]:g}"
                self._set_status(
                    f"Done. Click jump:{label} to annotate the timeline and jump there."
                )
            else:
                self._set_status("Done.")
            self._cleanup_worker()

        def _on_tool_action(self, action: str, batch_id: str) -> None:
            action = (action or "").lower()
            if action == "apply":
                self._apply_tool_batch(batch_id, skipped=False)
            elif action == "skip":
                self._apply_tool_batch(batch_id, skipped=True)
            elif action == "undo":
                if on_undo_tools:
                    on_undo_tools()
                batch = self._pending_batches.get(batch_id)
                if batch:
                    for t in batch.get("tools") or []:
                        t["status"] = "undone"
                    idx = int(batch.get("entry_index", -1))
                    if 0 <= idx < len(self._entries) and isinstance(self._entries[idx], dict):
                        self._entries[idx]["tools"] = batch["tools"]
                    self._refresh_log()
                self._set_status("Reverted last AI GUI actions.")

        def _apply_tool_batch(self, batch_id: str, *, skipped: bool) -> None:
            batch = self._pending_batches.get(batch_id)
            if not batch:
                return
            tools = list(batch.get("tools") or [])
            results: List[Dict[str, Any]] = []
            if skipped:
                for t in tools:
                    t["status"] = "skipped"
                    results.append(tool_result_payload(False, "User declined to apply this GUI action."))
            elif on_execute_tools or any(is_export_tool(str(t.get("name") or "")) for t in tools):
                host_tools = [t for t in tools if not is_export_tool(str(t.get("name") or ""))]
                host_results: List[Dict[str, Any]] = []
                if host_tools and on_execute_tools:
                    try:
                        host_results = list(on_execute_tools(host_tools) or [])
                    except Exception as exc:
                        host_results = [tool_result_payload(False, str(exc)) for _ in host_tools]
                hi = 0
                for t in tools:
                    if is_export_tool(str(t.get("name") or "")):
                        results.append(self._export_ai_report(
                            str(t.get("name") or ""),
                            t.get("arguments") if isinstance(t.get("arguments"), dict) else {}))
                    else:
                        res = (
                            host_results[hi]
                            if hi < len(host_results) and isinstance(host_results[hi], dict)
                            else tool_result_payload(False, "missing tool result")
                        )
                        hi += 1
                        results.append(res)
                for i, t in enumerate(tools):
                    res = results[i] if i < len(results) and isinstance(results[i], dict) else {}
                    t["status"] = "applied" if res.get("ok", True) else "failed"
                    t["result"] = res.get("message", "")
            else:
                for t in tools:
                    t["status"] = "skipped"
                    results.append(tool_result_payload(False, "No GUI dispatcher."))
            idx = int(batch.get("entry_index", -1))
            if 0 <= idx < len(self._entries) and isinstance(self._entries[idx], dict):
                self._entries[idx]["tools"] = tools
            self._refresh_log()

            for t, res in zip(tools, results or [tool_result_payload(False, "")] * len(tools)):
                self._chat_messages.append(tool_result_message(
                    tool_call_id=str(t.get("id") or ""),
                    name=str(t.get("name") or ""),
                    content=format_tool_result_content(
                        res if isinstance(res, dict) else tool_result_payload(False, str(res))
                    ),
                ))
                tool_name = str(t.get("name") or "")
                if tool_name in EVIDENCE_PANEL_TOOLS:
                    self._update_evidence_from_tool_result(
                        tool_name,
                        res if isinstance(res, dict) else {},
                    )
            if skipped:
                self._set_status("Skipped GUI actions.")
                self._cleanup_worker()
                return
            if self._tool_round >= max_tool_rounds(self._active_template_id):
                self._set_status("Done (tool round limit).")
                self._cleanup_worker()
                return
            self._tool_round += 1
            final_round = self._tool_round >= max_tool_rounds(self._active_template_id)
            self._continue_with_messages(final_round=final_round)

        def _continue_with_messages(self, final_round: bool = False) -> None:
            cfg = self._settings_dict()
            active = resolve_ai_settings(cfg)
            messages = list(self._chat_messages)
            if final_round:
                # Last allowed round: drop tools so the model must answer in
                # text now, instead of silently hitting the round cap next.
                messages.append({
                    "role": "user",
                    "content": (
                        "You have reached the tool-call limit for this turn. "
                        "Do not call any more tools — summarize your findings "
                        "and give your final answer now in plain text."
                    ),
                })
            kwargs = {
                "query": "",
                "messages": messages,
                "tools": [] if final_round else ai_viewer_tools(),
                "base_url": active["base_url"],
                "model": active["model"],
                "api_key": active["api_key"],
                "preset": active["preset"],
                "tls_verify": parse_ai_tls_verify(active.get("tls_verify")),
                "response_language": cfg.get(
                    "response_language", DEFAULT_AI_RESPONSE_LANGUAGE
                ),
                "log_mcp": parse_ai_mcp_log(cfg.get("mcp_log")),
            }
            self._set_busy(True)
            label = ai_preset_info(active["preset"])[1]
            self._set_status(f"Waiting for {label} ({active['model']})…")
            worker = _OllamaWorker(self, kwargs)
            worker.finished.connect(self._on_ok, Qt.ConnectionType.QueuedConnection)
            worker.failed.connect(self._on_err, Qt.ConnectionType.QueuedConnection)
            worker.cancelled.connect(self._on_cancelled, Qt.ConnectionType.QueuedConnection)
            self._worker = worker
            self._mark_cost_start()
            worker.start()

        def _on_err(self, msg: str) -> None:
            self._append("assistant", f"(Error) {msg}")
            self._set_status((msg or "").split("\n", 1)[0][:200], error=True)
            low = (msg or "").lower()
            if "http 401" in low or "http 403" in low or "api key required" in low:
                self._auth_forced = True
            self._refresh_auth_chip()
            self._cleanup_worker()

        def _on_cancelled(self) -> None:
            self._set_status("Stopped.")
            self._cleanup_worker()

        def send_current(self) -> None:
            if self._busy:
                return
            query = self._input.toPlainText().strip()
            if not query:
                return
            cfg = self._settings_dict()
            if str(cfg.get("enabled", "true")).lower() in ("0", "false", "no", "off"):
                self._set_status("AI is disabled in Settings → AI.")
                return

            ctx: Dict[str, Any] = {}
            if get_context:
                try:
                    ctx = normalize_ai_context(dict(get_context() or {}))
                except Exception as exc:
                    self._set_status(f"Context error: {exc}")
                    return

            skip = bool(getattr(self, "_skip_interpret", False))
            self._skip_interpret = False
            if should_confirm_interpreted_query(
                query, already_interpreted=skip,
            ):
                self._input.clear()
                self._append("user", query)
                cursors = list(ctx.get("cursors") or [])
                lo = hi = None
                if len(cursors) >= 2:
                    lo, hi = min(float(t) for t in cursors), max(float(t) for t in cursors)
                data = interpret_investigation_query(
                    query,
                    findings=list(ctx.get("findings") or []),
                    cursor_lo=lo,
                    cursor_hi=hi,
                )
                self._update_evidence_from_tool_result(
                    "interpret_query", {"ok": True, **data},
                )
                self._set_status(
                    "Confirm investigation scope, then Run investigation."
                )
                return
            self._input.clear()
            self._send_query(query, ctx)

        def _send_query(self, query: str, ctx: Dict[str, Any]) -> None:
            cfg = self._settings_dict()
            if str(cfg.get("enabled", "true")).lower() in ("0", "false", "no", "off"):
                self._set_status("AI is disabled in Settings → AI.")
                return

            ctx = normalize_ai_context(ctx)
            active = resolve_ai_settings(cfg)
            privacy = apply_cloud_privacy(
                ctx.get("findings_text", ""),
                query,
                endpoint_is_local=is_local_ai_host(active.get("base_url", "")),
                redact_task_names=str(cfg.get("redact_task_names", "")).lower()
                in ("1", "true", "yes", "on"),
                sensitive=str(cfg.get("trace_sensitive", "")).lower()
                in ("1", "true", "yes", "on"),
            )
            if privacy.get("blocked"):
                self._set_status(str(privacy.get("note") or "Cloud AI disabled."))
                return
            ctx["findings_text"] = privacy.get("findings_text") or ctx.get("findings_text", "")
            query = str(privacy.get("query") or query)
            self._append("user", query)
            self._tool_round = 0
            self._chat_messages = _build_chat_messages(
                query,
                findings_text=ctx.get("findings_text", ""),
                metrics=ctx.get("metrics"),
                span=ctx.get("span", ""),
                cores=ctx.get("cores", ""),
                scope=ctx.get("scope", ""),
                cursors=ctx.get("cursors"),
                response_language=cfg.get(
                    "response_language", DEFAULT_AI_RESPONSE_LANGUAGE
                ),
            )
            self._set_busy(True)
            label = ai_preset_info(active["preset"])[1]
            self._set_status(f"Waiting for {label} ({active['model']})…")

            kwargs = {
                "query": query,
                "messages": list(self._chat_messages),
                "tools": ai_viewer_tools(),
                "base_url": active["base_url"],
                "model": active["model"],
                "api_key": active["api_key"],
                "preset": active["preset"],
                "tls_verify": parse_ai_tls_verify(active.get("tls_verify")),
                "response_language": cfg.get(
                    "response_language", DEFAULT_AI_RESPONSE_LANGUAGE
                ),
                "log_mcp": parse_ai_mcp_log(cfg.get("mcp_log")),
            }
            # Worker stays on the GUI thread; only the HTTP call runs off-thread.
            worker = _OllamaWorker(self, kwargs)
            worker.finished.connect(self._on_ok, Qt.ConnectionType.QueuedConnection)
            worker.failed.connect(self._on_err, Qt.ConnectionType.QueuedConnection)
            worker.cancelled.connect(self._on_cancelled, Qt.ConnectionType.QueuedConnection)
            self._worker = worker
            self._mark_cost_start()
            worker.start()

        def _cleanup_worker(self) -> None:
            self._set_busy(False)
            worker = self._worker
            self._worker = None
            if worker is not None:
                try:
                    worker.finished.disconnect(self._on_ok)
                    worker.failed.disconnect(self._on_err)
                    worker.cancelled.disconnect(self._on_cancelled)
                except (TypeError, RuntimeError):
                    pass
                worker.deleteLater()

    return AiAssistantPanel()
