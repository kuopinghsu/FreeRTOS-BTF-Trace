#!/usr/bin/env python3
"""Export all AI system prompts, templates, and tool schemas to a review text file.

Desktop/Web lockstep sources:
  btf_viewer_pkg/ai_assistant.py, ai_tools.py, ai_case.py
  web/src/utils/aiClient.js, aiTools.js, aiCase.js

On-demand only (not part of ``make`` / ``make web`` / ``make bundle``):
  make -C BTFViewer ai-prompts
  python3 scripts/export_ai_prompts.py
  python3 scripts/export_ai_prompts.py -o /tmp/ai_prompts.txt
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from btf_viewer_pkg.ai_assistant import (  # noqa: E402
    AI_CORE_PROMPT,
    AI_SYSTEM_PROMPT,
    AI_TEMPLATE_QUESTIONS,
    AI_DEFAULT_TEMPLATE_ORDER,
    AI_TEMPLATE_MENU_GROUPS,
    AI_TEMPLATE_INTENT_GROUPS,
    AI_SMP_ONLY_TEMPLATE_IDS,
    AI_RESPONSE_LANGUAGES,
    DEFAULT_AI_RESPONSE_LANGUAGE,
    ASK_EVENT_PROMPT,
    build_ai_system_prompt,
    compose_ask_event_prompt,
)
from btf_viewer_pkg.ai_tools import (  # noqa: E402
    AI_TOOL_PROMPT,
    AI_TOOL_SYSTEM_ADDENDUM,
    ai_viewer_tools,
)
from btf_viewer_pkg.ai_case import (  # noqa: E402
    VALIDATE_EXPERIMENT_PROMPT,
    AI_CONTEXT_MODES,
    AI_CONTEXT_PROMPTS,
    INVESTIGATION_MODES,
    context_mode_system_addendum,
    investigation_mode_prompt,
    investigation_mode_plan,
    builtin_investigation_templates,
    investigation_template_prompt,
    interpreted_run_prompt,
)


def _section(lines: list[str], title: str, *, level: int = 1) -> None:
    bar = "=" if level == 1 else "-"
    lines.append("")
    lines.append(bar * 72)
    lines.append(title)
    lines.append(bar * 72)
    lines.append("")


def build_export_text() -> str:
    lines: list[str] = []
    _section(lines, "BTFViewer AI prompts — Desktop/Web lockstep export")
    lines.append("Source of truth (identical on Desktop and Web):")
    lines.append("  Desktop: btf_viewer_pkg/ai_assistant.py, ai_tools.py, ai_case.py")
    lines.append("  Web:     web/src/utils/aiClient.js, aiTools.js, aiCase.js")
    lines.append(f"Default reply language: {DEFAULT_AI_RESPONSE_LANGUAGE}")
    lines.append("Languages: " + ", ".join(AI_RESPONSE_LANGUAGES))
    lines.append(
        "SMP-only template ids: "
        + ", ".join(sorted(AI_SMP_ONLY_TEMPLATE_IDS))
    )
    lines.append(f"Template count: {len(AI_TEMPLATE_QUESTIONS)}")
    lines.append(f"Tool count: {len(ai_viewer_tools())}")

    _section(lines, "1. AI_CORE_PROMPT")
    lines.append(AI_CORE_PROMPT)

    _section(lines, "2. AI_TOOL_PROMPT (= AI_TOOL_SYSTEM_ADDENDUM)")
    lines.append(AI_TOOL_PROMPT)

    _section(lines, "3. AI_SYSTEM_PROMPT (CORE + TOOL prefix for caching)")
    lines.append(AI_SYSTEM_PROMPT)

    _section(lines, "4. AI_CONTEXT_PROMPTS")
    for mode in AI_CONTEXT_MODES:
        lines.append(f"--- mode: {mode} ---")
        lines.append(AI_CONTEXT_PROMPTS[mode])
        lines.append("")

    _section(lines, "5. build_ai_system_prompt(\"English\", \"balanced\") — full system message")
    lines.append(build_ai_system_prompt("English", "balanced"))

    _section(lines, "6. Template layout")
    lines.append("DEFAULT order: " + ", ".join(AI_DEFAULT_TEMPLATE_ORDER))
    lines.append("")
    lines.append("MENU groups:")
    for label, ids in AI_TEMPLATE_MENU_GROUPS:
        lines.append(f"  {label}: {', '.join(ids)}")
    lines.append("")
    lines.append("INTENT landing groups:")
    for label, ids in AI_TEMPLATE_INTENT_GROUPS:
        lines.append(f"  {label}: {', '.join(ids)}")

    _section(lines, "7. AI_TEMPLATE_QUESTIONS (user prompts)")
    for tid, lab, prompt in AI_TEMPLATE_QUESTIONS:
        lines.append(f"--- id={tid}  label={lab} ---")
        lines.append(prompt)
        lines.append("")

    _section(lines, "8. ASK_EVENT_PROMPT")
    lines.append(ASK_EVENT_PROMPT)
    lines.append("")
    lines.append("--- compose_ask_event_prompt(sample) ---")
    lines.append(compose_ask_event_prompt({
        "task": "ControlTask",
        "core": "Core_0",
        "ns": 1805120,
        "start": 1805000,
        "stop": 1806000,
    }))

    _section(lines, "9. VALIDATE_EXPERIMENT_PROMPT")
    lines.append(VALIDATE_EXPERIMENT_PROMPT)

    _section(lines, "10. Investigation-mode plans + prompts")
    for mode in INVESTIGATION_MODES:
        plan = investigation_mode_plan(mode)
        lines.append(f"--- mode: {mode} ---")
        lines.append(f"goal: {plan.get('goal')}")
        lines.append(f"template: {plan.get('template')}")
        tools = plan.get("tools") or []
        lines.append("tools: " + " → ".join(str(t) for t in tools))
        lines.append("")
        lines.append(investigation_mode_prompt(mode))
        lines.append("")

    _section(lines, "11. Builtin investigation templates (My Investigation)")
    for tpl in builtin_investigation_templates():
        tid = tpl.get("id")
        label = tpl.get("label")
        steps = tpl.get("steps") or []
        lines.append(f"--- id={tid}  label={label} ---")
        lines.append("steps: " + " → ".join(str(s) for s in steps))
        lines.append("")
        lines.append(investigation_template_prompt(tpl))
        lines.append("")

    _section(lines, "12. interpreted_run_prompt (sample)")
    lines.append(interpreted_run_prompt({
        "interpreted_question": "Find why ControlTask misses deadlines",
        "mode": "diagnose",
        "scope": ["execution", "blocking", "mutex"],
        "finding_id": "deadline_miss",
    }))

    _section(lines, "13. Tool schemas (name + description + parameters)")
    for t in ai_viewer_tools():
        fn = t.get("function") or {}
        name = fn.get("name") or "?"
        desc = (fn.get("description") or "").strip()
        lines.append(f"--- {name} ---")
        lines.append(desc)
        params = fn.get("parameters") or {}
        req = params.get("required") or []
        props = params.get("properties") or {}
        if props:
            lines.append("parameters:")
            for key, spec in props.items():
                star = " *" if key in req else ""
                typ = spec.get("type", "")
                pdesc = (spec.get("description") or "").strip()
                enum = spec.get("enum")
                extra = f" enum={enum}" if enum else ""
                lines.append(f"  - {key}{star} ({typ}): {pdesc}{extra}")
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "-o", "--output",
        type=Path,
        default=ROOT / "builds" / "ai_prompts_review.txt",
        help="Output text path (default: builds/ai_prompts_review.txt)",
    )
    args = ap.parse_args()
    text = build_export_text()
    out: Path = args.output
    if not out.is_absolute():
        out = ROOT / out
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(text, encoding="utf-8")
    print(f"Wrote {out} ({len(text)} bytes, {text.count(chr(10)) + 1} lines)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
