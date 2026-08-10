"""Viewer tool schemas + validation (Desktop/Web parity)."""
from __future__ import annotations

import json
import re
import sys
import unittest
from pathlib import Path

BTF_ROOT = Path(__file__).resolve().parents[1]
if str(BTF_ROOT) not in sys.path:
    sys.path.insert(0, str(BTF_ROOT))

from btf_viewer_pkg.ai_tools import (  # noqa: E402
    btf_highlight_href,
    btf_jump_href,
    parse_btf_highlight_href,
    parse_btf_jump_href,
    AI_TOOL_HIGHLIGHT_TASK,
    AI_TOOL_OPEN_CORRIDOR,
    AI_TOOL_SET_CURSORS,
    AI_TOOL_SET_VIEW_MODE,
    AI_TOOL_SYSTEM_ADDENDUM,
    AI_TOOL_ZOOM_TO_RANGE,
    AI_VIEWER_TOOL_NAMES,
    ai_viewer_tools,
    canonical_assistant_tool_message,
    extract_tool_calls,
    merge_tool_calls,
    normalize_tool_chat_messages,
    parse_ai_auto_apply,
    parse_tool_calls_from_text,
    resolve_core_key,
    resolve_task_key,
    strip_parsed_tool_markup,
    summarise_tool_call,
    tool_result_message,
    validate_tool_call,
)
from btf_viewer_pkg.parser import _task_merge_key  # noqa: E402


class AiToolsTests(unittest.TestCase):
    def test_schema_names(self) -> None:
        names = [t["function"]["name"] for t in ai_viewer_tools()]
        self.assertEqual(tuple(names), AI_VIEWER_TOOL_NAMES)

    def test_validate_set_cursors_and_zoom(self) -> None:
        args, err = validate_tool_call(
            AI_TOOL_SET_CURSORS, {"timestamps": [3099000, 3133000]})
        self.assertEqual(err, "")
        self.assertEqual(args["timestamps"], [3099000.0, 3133000.0])
        args, err = validate_tool_call(
            AI_TOOL_ZOOM_TO_RANGE, {"start_time": 20, "end_time": 10})
        self.assertEqual(err, "")
        self.assertEqual(args["start_time"], 10.0)
        self.assertEqual(args["end_time"], 20.0)
        _, err = validate_tool_call(AI_TOOL_SET_CURSORS, {"timestamps": []})
        self.assertIn("timestamps", err)
        args, err = validate_tool_call(
            AI_TOOL_SET_CURSORS, {"timestamps": list(range(12))})
        self.assertEqual(err, "")
        self.assertEqual(len(args["timestamps"]), 8)
        _, err = validate_tool_call(
            AI_TOOL_ZOOM_TO_RANGE, {"start_time": 5, "end_time": 5})
        self.assertIn("differ", err)

    def test_validate_highlight_view_and_corridor(self) -> None:
        args, err = validate_tool_call(
            AI_TOOL_HIGHLIGHT_TASK, {"task_name_or_id": "  PS[228] "})
        self.assertEqual(err, "")
        self.assertEqual(args["task_name_or_id"], "PS[228]")
        args, err = validate_tool_call(AI_TOOL_HIGHLIGHT_TASK, {"task_name_or_id": ""})
        self.assertEqual(err, "")
        self.assertEqual(args["task_name_or_id"], "")
        args, err = validate_tool_call(
            AI_TOOL_SET_VIEW_MODE, {"mode": "CORE", "orientation": "v"})
        self.assertEqual(err, "")
        self.assertEqual(args, {"mode": "core", "orientation": "vertical"})
        args, err = validate_tool_call(
            AI_TOOL_SET_VIEW_MODE, {"mode": "task", "orientation": "horiz"})
        self.assertEqual(args["orientation"], "horizontal")
        _, err = validate_tool_call(AI_TOOL_SET_VIEW_MODE, {"mode": "gantt"})
        self.assertIn("mode", err)
        args, err = validate_tool_call(
            AI_TOOL_OPEN_CORRIDOR, {"core_from": " 0 ", "core_to": "Core_1"})
        self.assertEqual(err, "")
        self.assertEqual(args, {"core_from": "0", "core_to": "Core_1"})
        args, err = validate_tool_call(AI_TOOL_OPEN_CORRIDOR, {})
        self.assertEqual(args, {"core_from": "", "core_to": ""})

    def test_summarise_each_viewer_tool(self) -> None:
        self.assertIn("10", summarise_tool_call(
            AI_TOOL_SET_CURSORS, {"timestamps": [10, 20]}))
        self.assertIn("Zoom to range", summarise_tool_call(
            AI_TOOL_ZOOM_TO_RANGE, {"start_time": 10, "end_time": 20}))
        self.assertIn("PS[228]", summarise_tool_call(
            AI_TOOL_HIGHLIGHT_TASK, {"task_name_or_id": "PS[228]"}))
        self.assertIn("Clear", summarise_tool_call(
            AI_TOOL_HIGHLIGHT_TASK, {"task_name_or_id": ""}))
        self.assertIn("core", summarise_tool_call(
            AI_TOOL_SET_VIEW_MODE, {"mode": "core", "orientation": "vertical"}))
        self.assertIn("Core_0", summarise_tool_call(
            AI_TOOL_OPEN_CORRIDOR, {"core_from": "Core_0", "core_to": "Core_1"}))
        self.assertEqual(
            summarise_tool_call(AI_TOOL_OPEN_CORRIDOR, {}),
            "Open corridor inspector",
        )

    def test_resolve_core_key(self) -> None:
        cores = ["Core_0", "Core_1", "Core_10"]
        self.assertEqual(resolve_core_key("Core_0", cores), "Core_0")
        self.assertEqual(resolve_core_key("0", cores), "Core_0")
        self.assertEqual(resolve_core_key("c1", cores), "Core_1")
        self.assertEqual(resolve_core_key("C0", cores), "Core_0")
        self.assertEqual(resolve_core_key("C1", cores), "Core_1")
        self.assertEqual(resolve_core_key("Core_2", ["Core_0", "Core_1", "Core_2"]), "Core_2")
        self.assertEqual(resolve_core_key("Core 10", cores), "Core_10")
        self.assertEqual(resolve_core_key("core_1", cores), "Core_1")
        self.assertIsNone(resolve_core_key("99", cores))
        self.assertIsNone(resolve_core_key("", cores))

    def test_summarise_and_extract(self) -> None:
        label = summarise_tool_call(
            AI_TOOL_SET_CURSORS, {"timestamps": [1, 2]})
        self.assertIn("1", label)
        self.assertIn("2", label)
        msg = {
            "tool_calls": [{
                "id": "c1",
                "function": {
                    "name": "highlight_task",
                    "arguments": json.dumps({"task_name_or_id": "Low[266]"}),
                },
            }],
        }
        calls = extract_tool_calls(msg)
        self.assertEqual(calls[0]["name"], "highlight_task")
        self.assertEqual(calls[0]["arguments"]["task_name_or_id"], "Low[266]")
        as_str = extract_tool_calls({
            "tool_calls": json.dumps([{
                "id": "c2",
                "name": "set_view_mode",
                "arguments": {"mode": "core"},
            }]),
        })
        self.assertEqual(as_str[0]["name"], "set_view_mode")
        self.assertEqual(as_str[0]["arguments"]["mode"], "core")

    def test_parse_btftool_fences_and_xml(self) -> None:
        text = (
            "Zooming in.\n"
            "```btftool\n"
            '{"name": "set_cursors", "arguments": {"timestamps": [10, 20]}}\n'
            "```\n"
            "<tool_call>\n"
            '{"name": "zoom_to_range", "arguments": {"start_time": 10, "end_time": 20}}\n'
            "</tool_call>\n"
            "```btftool\n"
            '{"name": "set_view_mode", "arguments": {"mode": "core", "orientation": "v"}}\n'
            "```\n"
            "```btftool\n"
            '{"name": "open_corridor_inspector", "arguments": {"core_from": "0", "core_to": "1"}}\n'
            "```\n"
        )
        calls = parse_tool_calls_from_text(text)
        names = [c["name"] for c in calls]
        self.assertEqual(names, [
            "set_cursors", "set_view_mode", "open_corridor_inspector", "zoom_to_range",
        ])
        self.assertEqual(calls[0]["arguments"]["timestamps"], [10.0, 20.0])
        self.assertEqual(calls[1]["arguments"]["orientation"], "vertical")
        self.assertEqual(calls[2]["arguments"]["core_from"], "0")
        stripped = strip_parsed_tool_markup(text)
        self.assertNotIn("btftool", stripped)
        self.assertNotIn("tool_call", stripped)
        merged = merge_tool_calls(
            [{"name": "set_cursors", "arguments": {"timestamps": [10.0, 20.0]}}],
            calls,
        )
        self.assertEqual(len(merged), 4)
        self.assertIn("```btftool", AI_TOOL_SYSTEM_ADDENDUM)

    def test_resolve_task_key(self) -> None:
        names = ["Idle[1]", "Low[266]", "High[268]"]
        self.assertEqual(resolve_task_key("Low[266]", names), "Low[266]")
        self.assertEqual(resolve_task_key("266", names), "Low[266]")
        self.assertEqual(resolve_task_key("high", names), "High[268]")
        ps = "\x00228\x00PS"
        low = "\x00266\x00Low"
        self.assertEqual(resolve_task_key("PS[228]", [ps, low]), ps)
        self.assertEqual(resolve_task_key("228", [ps, low]), ps)
        self.assertEqual(resolve_task_key("PS", [ps, low]), ps)
        self.assertEqual(
            resolve_task_key("Low[266] (Core 0)", ["Idle[1]", "Low[266]", "High[268]"]),
            "Low[266]",
        )
        self.assertIsNone(resolve_task_key("Mutex(0x80018700)", names))
        self.assertIsNone(resolve_task_key("Core_0", names))
        self.assertEqual(_task_merge_key("PS[228]"), ps)
        self.assertEqual(_task_merge_key(ps), ps)

    def test_btf_jump_and_highlight_hrefs(self) -> None:
        self.assertEqual(btf_jump_href(1805120), "btfjump:time/1805120")
        self.assertEqual(parse_btf_jump_href("btfjump:time/1805120"), 1805120.0)
        self.assertEqual(parse_btf_jump_href("btfjump:1805120"), 1805120.0)
        self.assertEqual(parse_btf_jump_href("btfjump://time/99.5"), 99.5)
        href = btf_highlight_href("PS[228]")
        self.assertTrue(href.startswith("btfhighlight:task/"))
        self.assertEqual(parse_btf_highlight_href(href), "PS[228]")
        self.assertEqual(parse_btf_highlight_href("btfhighlight:Low[266]"), "Low[266]")

    def test_auto_apply_default_off(self) -> None:
        self.assertFalse(parse_ai_auto_apply(None))
        self.assertFalse(parse_ai_auto_apply("false"))
        self.assertTrue(parse_ai_auto_apply("true"))

    def test_normalize_tool_messages_fills_gemini_function_names(self) -> None:
        asst = canonical_assistant_tool_message("Applying.", [
            {"id": "c1", "name": "set_cursors", "arguments": {"timestamps": [1, 2]}},
            {"id": "c2", "name": "highlight_task",
             "arguments": {"task_name_or_id": "PS[228]"}},
        ])
        self.assertEqual(asst["tool_calls"][0]["function"]["name"], "set_cursors")
        nameless = [
            {"role": "user", "content": "fix inversion"},
            asst,
            {"role": "tool", "tool_call_id": "c1", "content": '{"ok": true}'},
            {"role": "tool", "tool_call_id": "c2", "content": '{"ok": true}'},
        ]
        fixed = normalize_tool_chat_messages(nameless)
        tools = [m for m in fixed if m.get("role") == "tool"]
        self.assertEqual([m.get("name") for m in tools], [
            "set_cursors", "highlight_task",
        ])
        by_order = normalize_tool_chat_messages([
            asst,
            tool_result_message(tool_call_id="", name="", content={"ok": True}),
            {"role": "tool", "content": '{"ok": true}'},
        ])
        self.assertEqual(
            [m.get("name") for m in by_order if m.get("role") == "tool"],
            ["set_cursors", "highlight_task"],
        )
        self.assertTrue(all(m.get("tool_call_id") for m in by_order if m["role"] == "tool"))

    def test_tools_match_web(self) -> None:
        js = (BTF_ROOT / "web/src/utils/aiTools.js").read_text(encoding="utf-8")
        for name in AI_VIEWER_TOOL_NAMES:
            self.assertRegex(js, re.compile(rf"['\"]{re.escape(name)}['\"]"))
        self.assertIn("mermaid sequenceDiagram", AI_TOOL_SYSTEM_ADDENDUM)
        self.assertIn("mermaid sequenceDiagram", js)


if __name__ == "__main__":
    unittest.main()
