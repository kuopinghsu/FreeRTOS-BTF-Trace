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
    AI_TOOL_SET_CURSORS,
    AI_TOOL_SYSTEM_ADDENDUM,
    AI_VIEWER_TOOL_NAMES,
    ai_viewer_tools,
    extract_tool_calls,
    merge_tool_calls,
    parse_ai_auto_apply,
    parse_tool_calls_from_text,
    resolve_task_key,
    strip_parsed_tool_markup,
    summarise_tool_call,
    validate_tool_call,
)


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
            "zoom_to_range", {"start_time": 20, "end_time": 10})
        self.assertEqual(err, "")
        self.assertEqual(args["start_time"], 10.0)
        self.assertEqual(args["end_time"], 20.0)

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
        )
        calls = parse_tool_calls_from_text(text)
        names = [c["name"] for c in calls]
        self.assertEqual(names, ["set_cursors", "zoom_to_range"])
        self.assertEqual(calls[0]["arguments"]["timestamps"], [10.0, 20.0])
        stripped = strip_parsed_tool_markup(text)
        self.assertNotIn("btftool", stripped)
        self.assertNotIn("tool_call", stripped)
        merged = merge_tool_calls(
            [{"name": "set_cursors", "arguments": {"timestamps": [10.0, 20.0]}}],
            calls,
        )
        self.assertEqual(len(merged), 2)
        self.assertIn("```btftool", AI_TOOL_SYSTEM_ADDENDUM)

    def test_resolve_task_key(self) -> None:
        names = ["Idle[1]", "Low[266]", "High[268]"]
        self.assertEqual(resolve_task_key("Low[266]", names), "Low[266]")
        self.assertEqual(resolve_task_key("266", names), "Low[266]")
        self.assertEqual(resolve_task_key("high", names), "High[268]")

    def test_auto_apply_default_off(self) -> None:
        self.assertFalse(parse_ai_auto_apply(None))
        self.assertFalse(parse_ai_auto_apply("false"))
        self.assertTrue(parse_ai_auto_apply("true"))

    def test_tools_match_web(self) -> None:
        js = (BTF_ROOT / "web/src/utils/aiTools.js").read_text(encoding="utf-8")
        for name in AI_VIEWER_TOOL_NAMES:
            self.assertRegex(js, re.compile(rf"['\"]{re.escape(name)}['\"]"))
        self.assertIn("mermaid sequenceDiagram", AI_TOOL_SYSTEM_ADDENDUM)
        self.assertIn("mermaid sequenceDiagram", js)


if __name__ == "__main__":
    unittest.main()
