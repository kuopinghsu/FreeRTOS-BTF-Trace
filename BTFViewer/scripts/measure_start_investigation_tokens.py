#!/usr/bin/env python3
"""Measure Start Investigation request packing (token estimate).

Breaks one Start Investigation (= auto_investigate) pack into:
  system / findings / user question / tool schemas
and then simulates five typical tool rounds to show cumulative prompt growth.

Usage:
  PYTHONPATH=. QT_QPA_PLATFORM=offscreen \\
    python3 scripts/measure_start_investigation_tokens.py \\
      [../tracedata/example-8cores.btf.gz]
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from btf_viewer_pkg._bootstrap import install  # noqa: E402

install()

from PySide6.QtWidgets import QApplication  # noqa: E402

from btf_viewer_pkg.ai_assistant import (  # noqa: E402
    _build_chat_messages,
    ai_template_by_id,
    build_ai_system_prompt,
)
from btf_viewer_pkg.ai_case import (  # noqa: E402
    compact_tool_result_payload,
    investigation_context_summary,
    tool_names_for_context_mode,
)
from btf_viewer_pkg.ai_investigation import (  # noqa: E402
    build_investigate_context,
    enrich_findings_with_ids,
)
from btf_viewer_pkg.ai_tools import (  # noqa: E402
    ai_viewer_tools_for_mode,
    tool_result_message,
)
from btf_viewer_pkg.parser import (  # noqa: E402
    _blocking_time_rows_export_like,
    _core_pair_rows,
    _core_util_pct_for,
    _migration_rows,
    _parse_btf,
    _priority_stats_rows,
    _sync_object_stats_rows,
    _tick_health_report,
)
from btf_viewer_pkg.stats import (  # noqa: E402
    _build_workflow_analysis_findings,
    _format_analysis_findings_text,
)


def _est_tok(text: str) -> int:
    """Rough OpenAI-ish estimate: ~4 chars/token."""
    return max(0, (len(text) + 3) // 4)


def _blocking_rows(trace, lo, hi):
    # Prefer stats export helper when present; else empty.
    try:
        from btf_viewer_pkg.stats import StatisticsView  # type: ignore
    except Exception:
        pass
    # Use parser-level blocking if available via a light local rebuild.
    try:
        from btf_viewer_pkg.parser import _task_blocking_rows  # type: ignore
        return _task_blocking_rows(trace, lo, hi)
    except Exception:
        return []


def _exec_rows(trace, lo, hi):
    try:
        from btf_viewer_pkg.parser import _task_exec_slice_rows  # type: ignore
        return _task_exec_slice_rows(trace, lo, hi)
    except Exception:
        return []


def build_findings(trace) -> Tuple[List[dict], str]:
    lo = hi = None
    core_rows = [(c, _core_util_pct_for(trace, c)) for c in (trace.core_names or [])]
    # Pull export-quality rows via StatsPanel methods without constructing UI:
    # duplicate the private helpers used by build_analysis_findings where possible.
    from btf_viewer_pkg import stats as stats_mod

    class _Shim:
        _cpu_budget_pct = 0
        _task_deadlines_ns = {}

        def _exec_slice_rows_export(self, tr, lo, hi):
            return stats_mod.StatisticsPanel._exec_slice_rows_export(self, tr, lo, hi)

        def _blocking_time_rows_export(self, tr, lo, hi):
            return stats_mod.StatisticsPanel._blocking_time_rows_export(self, tr, lo, hi)

        def _append_exec_anomaly_findings(self, findings, tr, lo, hi):
            return stats_mod.StatisticsPanel._append_exec_anomaly_findings(
                self, findings, tr, lo, hi)

        def _core_util_rows(self, tr, lo, hi):
            return [(c, _core_util_pct_for(tr, c)) for c in (tr.core_names or [])]

    shim = _Shim()
    # StatisticsPanel methods expect self attributes; bind unbound carefully.
    try:
        exec_rows = stats_mod.StatisticsPanel._exec_slice_rows_export(shim, trace, lo, hi)
    except Exception:
        exec_rows = []
    try:
        block_rows = stats_mod.StatisticsPanel._blocking_time_rows_export(shim, trace, lo, hi)
    except Exception:
        block_rows = []
    mig_rows = _migration_rows(trace, lo, hi)
    pair_rows = _core_pair_rows(trace, lo, hi)
    priority_rows = _priority_stats_rows(trace, lo, hi)
    sync_rows = _sync_object_stats_rows(trace, lo, hi)
    sync_issues = list(getattr(trace, "sync_issues", None) or [])
    tick = _tick_health_report(trace, lo, hi)
    findings = _build_workflow_analysis_findings(
        core_rows=core_rows,
        exec_rows=exec_rows,
        block_rows=block_rows,
        mig_rows=mig_rows,
        pair_rows=pair_rows,
        priority_rows=priority_rows,
        sync_rows=sync_rows,
        sync_issues=sync_issues,
        tick=tick,
        deadline_viols=None,
        time_scale=trace.time_scale,
    )
    try:
        findings = stats_mod.StatisticsPanel._append_exec_anomaly_findings(
            shim, findings, trace, lo, hi)
    except Exception:
        findings = enrich_findings_with_ids(findings)
    return findings, ""


def measure_mode(
    *,
    mode: str,
    findings: List[dict],
    findings_text: str,
    trace,
    prompt: str,
) -> Dict[str, Any]:
    system = build_ai_system_prompt("English", context_mode=mode)
    tools = ai_viewer_tools_for_mode(mode, "investigate")
    tool_blob = json.dumps(tools, default=str)
    names = tool_names_for_context_mode(mode, "investigate")

    messages = _build_chat_messages(
        prompt,
        findings_text=findings_text,
        findings=findings,
        span=f"{trace.time_max - trace.time_min} {trace.time_scale}",
        cores=len(trace.core_names or []),
        scope="full trace",
        cursors=[],
        response_language="English",
        context_mode=mode,
        investigation_summary="",
        trace_time_unit=str(trace.time_scale or ""),
    )
    user = next(
        (str(m.get("content") or "") for m in messages if m.get("role") == "user"),
        "",
    )
    # Split user blob roughly
    findings_part = ""
    if "### Analysis Findings" in user:
        findings_part = user.split("### Analysis Findings", 1)[1]
        if "### User Question" in findings_part:
            findings_part = findings_part.split("### User Question", 1)[0]
    question_part = prompt

    round0 = {
        "system_tok": _est_tok(system),
        "findings_tok": _est_tok(findings_part),
        "question_tok": _est_tok(question_part),
        "user_total_tok": _est_tok(user),
        "tool_schema_tok": _est_tok(tool_blob),
        "tool_schema_count": len(tools),
        "tool_names": None if names is None else len(names),
        "request_tok_est": _est_tok(system) + _est_tok(user) + _est_tok(tool_blob),
        "findings_raw_chars": len(findings_text),
        "findings_packed_chars": len(findings_part),
        "findings_count": len(findings),
    }

    # Simulate 5 tool rounds typical of auto_investigate.
    inv = build_investigate_context(findings=findings, finding_id="")
    inv_payload = compact_tool_result_payload(
        {"ok": True, "message": "investigate", "data": inv}, mode)
    synthetic = [
        ("investigate", inv_payload),
        ("correlate_events", compact_tool_result_payload({
            "ok": True, "message": "correlate",
            "data": {"events": [{"t": i, "label": f"ev{i}"} for i in range(40)]},
        }, mode)),
        ("verify_claim", compact_tool_result_payload({
            "ok": True, "message": "verify",
            "data": {"verdict": "inconclusive", "evidence": ["a", "b"]},
        }, mode)),
        ("challenge_conclusion", compact_tool_result_payload({
            "ok": True, "message": "challenge",
            "data": {"alternatives": [f"alt{i}" for i in range(8)]},
        }, mode)),
        ("set_cursors", compact_tool_result_payload({
            "ok": True, "message": "cursors set",
            "data": {"timestamps": [1, 2]},
        }, mode)),
    ]

    chat = list(messages)
    cumulative = []
    for i, (name, payload) in enumerate(synthetic, 1):
        chat.append({
            "role": "assistant",
            "content": "",
            "tool_calls": [{
                "id": f"c{i}",
                "type": "function",
                "function": {"name": name, "arguments": "{}"},
            }],
        })
        chat.append(tool_result_message(
            f"c{i}", name,
            json.dumps(payload, default=str) if not isinstance(payload, str) else payload,
        ))
        # Re-send estimate: system + full chat + tool schemas (provider typically
        # re-includes tools each round).
        body = json.dumps(chat, default=str)
        req = _est_tok(system) + _est_tok(body) + _est_tok(tool_blob)
        cumulative.append({
            "after_tool": name,
            "chat_tok": _est_tok(body),
            "request_tok_est": req,
            "tool_result_tok": _est_tok(
                json.dumps(payload, default=str) if not isinstance(payload, str)
                else payload),
        })

    # Investigation summary after tools (host-side)
    summary = investigation_context_summary({
        "investigation_case": {
            "goal": (findings[0].get("title") if findings else "finding"),
            "tools_executed": [n for n, _ in synthetic],
            "hypotheses": (inv.get("hypotheses") if isinstance(inv, dict) else []) or [],
        },
        "finding": findings[0] if findings else {},
        "evidence_quality": {"band": "medium"},
    })

    return {
        "mode": mode,
        "round0": round0,
        "after_5_tools": cumulative[-1] if cumulative else {},
        "per_tool": cumulative,
        "investigation_summary_tok": _est_tok(summary),
        "investigation_summary_chars": len(summary),
    }


def main(argv: List[str]) -> int:
    QApplication.instance() or QApplication([])
    default = ROOT.parent / "tracedata" / "example-8cores.btf.gz"
    path = Path(argv[1] if len(argv) > 1 else default).resolve()
    if not path.is_file():
        print(f"error: trace not found: {path}", file=sys.stderr)
        return 2

    trace = _parse_btf(str(path))
    findings, scope = build_findings(trace)
    findings_text = _format_analysis_findings_text(findings, scope)
    _tid, _lab, prompt = ai_template_by_id("auto_investigate")

    report: Dict[str, Any] = {
        "trace": str(path),
        "cores": len(trace.core_names or []),
        "time_scale": trace.time_scale,
        "findings_count": len(findings),
        "findings_raw_chars": len(findings_text),
        "findings_raw_tok_est": _est_tok(findings_text),
        "auto_investigate_prompt_tok": _est_tok(prompt),
        "note": (
            "Token estimates use chars/4. Provider prompt_tokens for a live "
            "session sum across rounds; after_5_tools.request_tok_est is the "
            "size of the *last* request (includes prior tool results)."
        ),
        "modes": {},
    }

    lines = [
        f"# Start Investigation token breakdown",
        f"",
        f"Trace: `{path.name}`  cores={report['cores']}  "
        f"findings={report['findings_count']}  "
        f"raw findings ≈ {report['findings_raw_tok_est']} tok",
        f"",
        f"Start Investigation template (`auto_investigate`) ≈ "
        f"{report['auto_investigate_prompt_tok']} tok",
        f"",
        f"{report['note']}",
        f"",
    ]

    for mode in ("compact", "balanced", "full"):
        m = measure_mode(
            mode=mode,
            findings=findings,
            findings_text=findings_text,
            trace=trace,
            prompt=prompt,
        )
        report["modes"][mode] = m
        r0 = m["round0"]
        last = m["after_5_tools"]
        lines += [
            f"## Mode: {mode}",
            f"",
            f"| Bucket | ≈ tokens |",
            f"| --- | ---: |",
            f"| System prompt | {r0['system_tok']} |",
            f"| Findings (packed) | {r0['findings_tok']} |",
            f"| User question | {r0['question_tok']} |",
            f"| Tool schemas ({r0['tool_schema_count']} tools) | {r0['tool_schema_tok']} |",
            f"| **First request total** | **{r0['request_tok_est']}** |",
            f"| After 5 tool rounds (last request) | {last.get('request_tok_est', 0)} |",
            f"",
            f"Packed findings chars: {r0['findings_packed_chars']} "
            f"(raw {r0['findings_raw_chars']})",
            f"",
        ]
        lines.append("Per-tool cumulative last-request estimate:")
        for row in m["per_tool"]:
            lines.append(
                f"- after `{row['after_tool']}`: "
                f"tool_result≈{row['tool_result_tok']} tok, "
                f"request≈{row['request_tok_est']} tok"
            )
        lines.append("")

    out = ROOT / "builds" / "start_investigation_token_breakdown.md"
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    json_out = ROOT / "builds" / "start_investigation_token_breakdown.json"
    json_out.write_text(json.dumps(report, indent=2, default=str) + "\n", encoding="utf-8")
    print("\n".join(lines))
    print(f"Wrote {out}")
    print(f"Wrote {json_out}")
    return 0


if __name__ == "__main__":
    # Avoid unused import warnings in some linters
    _ = (_blocking_rows, _exec_rows, _blocking_time_rows_export_like)
    raise SystemExit(main(sys.argv))
