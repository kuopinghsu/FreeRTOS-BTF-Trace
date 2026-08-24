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
    btf_range_href,
    parse_btf_highlight_href,
    parse_btf_jump_href,
    parse_btf_range_href,
    AI_RAW_METRIC_PRIORITY,
    AI_TOOL_ADD_ANNOTATION,
    AI_TOOL_CLEAR_MARKS,
    AI_TOOL_EXPORT_REPORT,
    AI_TOOL_FIND_CRITICAL_PATH,
    AI_TOOL_GENERATE_REPORT,
    AI_TOOL_HIGHLIGHT_TASK,
    AI_TOOL_OPEN_CORRIDOR,
    AI_TOOL_QUERY_RAW_METRIC,
    AI_TOOL_RESET_VIEW,
    AI_TOOL_SEARCH_TIMELINE,
    AI_TOOL_SET_CURSORS,
    AI_TOOL_SET_VIEW_MODE,
    AI_TOOL_SYSTEM_ADDENDUM,
    AI_TOOL_TRIGGER_COMPARE,
    AI_TOOL_ZOOM_TO_RANGE,
    AI_VIEWER_TOOL_NAMES,
    ai_viewer_tools,
    ai_viewer_tools_for_mode,
    build_ai_report_csv,
    build_ai_report_html,
    GEMINI_SKIP_THOUGHT_SIGNATURE,
    canonical_assistant_tool_message,
    ensure_gemini_thought_signatures,
    extract_tool_calls,
    merge_tool_calls,
    needs_gemini_thought_signatures,
    normalize_raw_metric,
    normalize_tool_chat_messages,
    parse_ai_auto_apply,
    parse_ai_mcp_log,
    parse_tool_calls_from_text,
    is_query_tool,
    query_raw_metric,
    resolve_core_key,
    resolve_task_key,
    correlate_task_events,
    search_timeline_hits,
    strip_parsed_tool_markup,
    summarise_tool_call,
    tool_batch_auto_runs,
    tool_mutates_gui,
    tool_result_message,
    validate_tool_call,
)
from btf_viewer_pkg.parser import _task_merge_key  # noqa: E402


class AiToolsTests(unittest.TestCase):
    def test_schema_names(self) -> None:
        names = [t["function"]["name"] for t in ai_viewer_tools()]
        self.assertEqual(tuple(names), AI_VIEWER_TOOL_NAMES)

    def test_schema_names_for_compact_mode(self) -> None:
        names = [
            t["function"]["name"]
            for t in ai_viewer_tools_for_mode("compact", "triage")
        ]
        self.assertIn("detect_anomalies", names)
        self.assertIn("query_raw_metric", names)
        self.assertNotIn("what_if", names)
        self.assertLess(len(names), len(AI_VIEWER_TOOL_NAMES))
        full = [
            t["function"]["name"]
            for t in ai_viewer_tools_for_mode("full", "triage")
        ]
        self.assertEqual(tuple(full), AI_VIEWER_TOOL_NAMES)

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

    def test_validate_annotation_query_and_export(self) -> None:
        args, err = validate_tool_call(
            AI_TOOL_ADD_ANNOTATION, {"time": 1805120, "note": "  spike  "})
        self.assertEqual(err, "")
        self.assertEqual(args["time"], 1805120.0)
        self.assertEqual(args["note"], "spike")
        _, err = validate_tool_call(AI_TOOL_ADD_ANNOTATION, {"time": 1, "note": ""})
        self.assertIn("note", err)
        args, err = validate_tool_call(
            AI_TOOL_QUERY_RAW_METRIC, {"task": "Low[266]", "metric": "pi"})
        self.assertEqual(err, "")
        self.assertEqual(args["metric"], AI_RAW_METRIC_PRIORITY)
        _, err = validate_tool_call(
            AI_TOOL_QUERY_RAW_METRIC, {"task": "Low[266]", "metric": "nope"})
        self.assertIn("metric", err)
        args, err = validate_tool_call(AI_TOOL_EXPORT_REPORT, {})
        self.assertEqual(err, "")
        self.assertEqual(args["format"], "html")
        args, err = validate_tool_call(AI_TOOL_EXPORT_REPORT, {"format": "CSV"})
        self.assertEqual(args["format"], "csv")
        self.assertIn("1805120", summarise_tool_call(
            AI_TOOL_ADD_ANNOTATION, {"time": 1805120, "note": "spike"}))
        self.assertIn("priority_inheritance", summarise_tool_call(
            AI_TOOL_QUERY_RAW_METRIC, {"task": "Low[266]", "metric": "pi"}))
        self.assertIn("csv", summarise_tool_call(
            AI_TOOL_EXPORT_REPORT, {"format": "csv"}))
        self.assertTrue(tool_mutates_gui(AI_TOOL_ADD_ANNOTATION))
        self.assertFalse(tool_mutates_gui(AI_TOOL_QUERY_RAW_METRIC))
        self.assertTrue(tool_batch_auto_runs([
            {"name": AI_TOOL_QUERY_RAW_METRIC},
        ]))
        self.assertTrue(tool_batch_auto_runs([
            {"name": AI_TOOL_EXPORT_REPORT},
        ]))
        self.assertTrue(tool_batch_auto_runs([
            {"name": AI_TOOL_GENERATE_REPORT},
            {"name": AI_TOOL_EXPORT_REPORT},
        ]))
        self.assertFalse(tool_batch_auto_runs([
            {"name": AI_TOOL_QUERY_RAW_METRIC},
            {"name": AI_TOOL_ADD_ANNOTATION},
        ]))
        self.assertEqual(normalize_raw_metric("L/M/H inversion"), "")
        self.assertEqual(normalize_raw_metric("priority-inheritance"), AI_RAW_METRIC_PRIORITY)

    def test_validate_clear_search_reset_compare(self) -> None:
        args, err = validate_tool_call(AI_TOOL_CLEAR_MARKS, {})
        self.assertEqual(err, "")
        self.assertEqual(args["what"], "all")
        args, err = validate_tool_call(AI_TOOL_CLEAR_MARKS, {"what": "marks"})
        self.assertEqual(args["what"], "all")
        _, err = validate_tool_call(AI_TOOL_CLEAR_MARKS, {"what": "nope"})
        self.assertIn("what", err)
        args, err = validate_tool_call(AI_TOOL_RESET_VIEW, {})
        self.assertEqual(err, "")
        self.assertEqual(args, {})
        args, err = validate_tool_call(
            AI_TOOL_SEARCH_TIMELINE, {"query": "TICK", "mode": "tags"})
        self.assertEqual(err, "")
        self.assertEqual(args["mode"], "tags")
        _, err = validate_tool_call(AI_TOOL_SEARCH_TIMELINE, {"query": ""})
        self.assertIn("query", err)
        args, err = validate_tool_call(
            AI_TOOL_TRIGGER_COMPARE, {"tab_a": "0", "tab_b": "tickless"})
        self.assertEqual(err, "")
        self.assertEqual(args["tab_b"], "tickless")
        self.assertTrue(is_query_tool(AI_TOOL_SEARCH_TIMELINE))
        self.assertTrue(is_query_tool(AI_TOOL_TRIGGER_COMPARE))
        self.assertTrue(is_query_tool("what_if"))
        self.assertTrue(is_query_tool("optimize_experiment"))
        self.assertFalse(is_query_tool(AI_TOOL_CLEAR_MARKS))
        self.assertTrue(tool_mutates_gui(AI_TOOL_CLEAR_MARKS))
        self.assertTrue(tool_mutates_gui(AI_TOOL_RESET_VIEW))
        self.assertTrue(tool_batch_auto_runs([{"name": AI_TOOL_SEARCH_TIMELINE}]))
        self.assertTrue(tool_batch_auto_runs([{"name": AI_TOOL_TRIGGER_COMPARE}]))
        self.assertFalse(tool_batch_auto_runs([
            {"name": AI_TOOL_SEARCH_TIMELINE},
            {"name": AI_TOOL_CLEAR_MARKS},
        ]))
        self.assertIn("all", summarise_tool_call(AI_TOOL_CLEAR_MARKS, {"what": "all"}))
        self.assertEqual(summarise_tool_call(AI_TOOL_RESET_VIEW, {}), "Reset view")
        self.assertIn("TICK", summarise_tool_call(
            AI_TOOL_SEARCH_TIMELINE, {"query": "TICK", "mode": "sti"}))

    def test_search_timeline_hits_annotations(self) -> None:
        from types import SimpleNamespace

        from btf_viewer_pkg.parser import BtfTrace  # noqa: WPS433

        trace = BtfTrace(
            time_scale="us",
            tasks=[],
            segments=[],
            sti_events=[],
            sti_channels=[],
            sti_events_by_target={},
            time_min=0,
            time_max=1000,
        )
        out = search_timeline_hits(
            trace, "watch", "contains",
            annotations=[SimpleNamespace(ns=500, note="watchdog timeout")],
        )
        self.assertTrue(out["ok"])
        self.assertEqual(out["data"]["times"], [500])
        self.assertEqual(out["data"]["count"], 1)
        bad_q = search_timeline_hits(trace, "", "contains")
        self.assertFalse(bad_q["ok"])
        bad_re = search_timeline_hits(trace, "[", "regex")
        self.assertFalse(bad_re["ok"])
        self.assertIn("Regex", bad_re["message"])

    def test_correlate_task_events_uses_search_without_unbound_local(self) -> None:
        from btf_viewer_pkg.parser import BtfTrace  # noqa: WPS433

        trace = BtfTrace(
            time_scale="us",
            tasks=["Med[267]"],
            segments=[],
            sti_events=[],
            sti_channels=[],
            sti_events_by_target={},
            time_min=0,
            time_max=1000,
        )
        out = correlate_task_events(trace, "Med[267]")
        self.assertIsInstance(out, dict)
        self.assertIn("ok", out)
        # Must not surface the monolith UnboundLocalError message.
        self.assertNotIn("_recompute_find_hits", str(out.get("message") or ""))
        self.assertNotIn("not associated with a value", str(out.get("message") or ""))

    def test_find_critical_path_accepts_singleton_timestamp_array(self) -> None:
        """JS Number([3087194]) works; Desktop must coerce the same LLM shape."""
        args, err = validate_tool_call(
            AI_TOOL_FIND_CRITICAL_PATH,
            {"task": "Med[267]", "timestamp": [3087194]},
        )
        self.assertEqual(err, "")
        self.assertEqual(args["task"], "Med[267]")
        self.assertEqual(args["timestamp"], 3087194.0)
        label = summarise_tool_call(
            AI_TOOL_FIND_CRITICAL_PATH,
            {"task": "Med[267]", "timestamp": [3087194]},
        )
        self.assertIn("3087194", label)
        self.assertNotIn("[3087194]", label)

    def test_task_match_aliases_med267_bracket_id(self) -> None:
        """Name[id] must yield id/prefix aliases even if _TASK_ID_* patterns collide."""
        from btf_viewer_pkg.ai_tools import _task_match_aliases, task_lookup_keys

        aliases = _task_match_aliases("Med[267]")
        self.assertIn("Med[267]", aliases)
        self.assertIn("267", aliases)
        self.assertIn("Med", aliases)
        self.assertIn("267", task_lookup_keys("Med[267]"))

    def test_correlate_survives_bad_annotations(self) -> None:
        """Odd annotation objects must not abort correlate / critical path."""
        from btf_viewer_pkg.ai_tools import find_critical_path_task  # noqa: WPS433
        from btf_viewer_pkg.parser import BtfTrace  # noqa: WPS433

        trace = BtfTrace(
            time_scale="us",
            tasks=["Med[267]"],
            segments=[],
            sti_events=[],
            sti_channels=[],
            sti_events_by_target={},
            time_min=0,
            time_max=1000,
        )
        out = find_critical_path_task(
            trace,
            "Med[267]",
            timestamp=3087194,
            annotations=[object()],  # no .note — previously raised AttributeError
        )
        self.assertIsInstance(out, dict)
        self.assertIn("ok", out)
        self.assertNotIn("AttributeError", str(out.get("message") or ""))
        self.assertNotIn("has no attribute", str(out.get("message") or ""))
        # Search failure must not poison the tool result shape.
        corr = correlate_task_events(
            trace, "Med[267]", annotations=[object()],
        )
        self.assertTrue(corr.get("ok"), corr.get("message"))

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

    def test_parse_btftool_ndjson_fence(self) -> None:
        """Models often emit several tool objects in one fence (not a JSON array)."""
        text = (
            "Focusing the segment.\n"
            "```btftool\n"
            '{"name": "set_cursors", "arguments": {"timestamps": [1036516, 1036826]}}\n'
            '{"name": "highlight_task", "arguments": {"task_name_or_id": "CS[24]"}}\n'
            '{"name": "zoom_to_range", "arguments": {"start_time": 1036400, "end_time": 1037000}}\n'
            "```\n"
        )
        calls = parse_tool_calls_from_text(text)
        self.assertEqual(
            [c["name"] for c in calls],
            ["set_cursors", "highlight_task", "zoom_to_range"],
        )
        self.assertEqual(calls[0]["arguments"]["timestamps"], [1036516.0, 1036826.0])
        self.assertEqual(calls[1]["arguments"]["task_name_or_id"], "CS[24]")
        self.assertEqual(calls[2]["arguments"]["start_time"], 1036400.0)
        stripped = strip_parsed_tool_markup(text)
        self.assertNotIn("btftool", stripped)
        self.assertNotIn("set_cursors", stripped)
        self.assertIn("Focusing the segment.", stripped)

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
        self.assertEqual(btf_range_href(1000, 2000), "btfrange:1000/2000")
        self.assertEqual(parse_btf_range_href("btfrange:1000/2000"), (1000.0, 2000.0))

    def test_auto_apply_default_off(self) -> None:
        self.assertFalse(parse_ai_auto_apply(None))
        self.assertFalse(parse_ai_auto_apply("false"))
        self.assertTrue(parse_ai_auto_apply("true"))

    def test_mcp_log_default_off(self) -> None:
        self.assertFalse(parse_ai_mcp_log(None))
        self.assertFalse(parse_ai_mcp_log("false"))
        self.assertTrue(parse_ai_mcp_log("true"))
        self.assertTrue(parse_ai_mcp_log("on"))

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

        empty_ids = [
            {"role": "user", "content": "fix inversion"},
            {
                "role": "assistant",
                "content": None,
                "tool_calls": [
                    {
                        "id": "",
                        "type": "function",
                        "function": {"name": "investigate", "arguments": "{}"},
                    },
                    {
                        "id": "",
                        "type": "function",
                        "function": {"name": "query_raw_metric", "arguments": "{}"},
                    },
                ],
            },
            {"role": "tool", "tool_call_id": "", "content": '{"ok": true}'},
            {"role": "tool", "content": '{"ok": true}'},
        ]
        fixed_ids = normalize_tool_chat_messages(empty_ids)
        asst_ids = [c["id"] for c in fixed_ids[1]["tool_calls"]]
        self.assertEqual(asst_ids, ["call_0", "call_1"])
        self.assertTrue(all(asst_ids))
        tools = [m for m in fixed_ids if m.get("role") == "tool"]
        self.assertEqual([m.get("name") for m in tools], [
            "investigate", "query_raw_metric",
        ])
        self.assertEqual(
            [m.get("tool_call_id") for m in tools], ["call_0", "call_1"])
        nested = extract_tool_calls({
            "tool_calls": [{
                "id": "",
                "function": {"arguments": "{}"},
                "extra_content": {
                    "google": {"function_call": {"name": "investigate"}},
                },
            }],
        })
        self.assertEqual(nested[0]["name"], "investigate")
        self.assertEqual(nested[0]["id"], "call_0")
        parts = extract_tool_calls({
            "content": [{
                "functionCall": {"name": "query_raw_metric", "args": {"metric": "sync"}},
            }],
        })
        self.assertEqual(parts[0]["name"], "query_raw_metric")
        self.assertEqual(parts[0]["arguments"]["metric"], "sync")

    def test_gemini_thought_signatures_roundtrip_and_skip(self) -> None:
        sig = "CvcQAdHtimRealSignature=="
        msg = {
            "role": "assistant",
            "content": None,
            "tool_calls": [
                {
                    "id": "c1",
                    "type": "function",
                    "function": {
                        "name": "set_cursors",
                        "arguments": '{"timestamps":[1,2]}',
                    },
                    "extra_content": {
                        "google": {"thought_signature": sig},
                    },
                },
                {
                    "id": "c2",
                    "type": "function",
                    "function": {
                        "name": "highlight_task",
                        "arguments": '{"task_name_or_id":"PS[228]"}',
                    },
                },
            ],
        }
        extracted = extract_tool_calls(msg)
        self.assertEqual(extracted[0]["thought_signature"], sig)
        self.assertNotIn("thought_signature", extracted[1])
        canon = canonical_assistant_tool_message(None, extracted)
        self.assertEqual(
            canon["tool_calls"][0]["extra_content"]["google"]["thought_signature"],
            sig,
        )
        self.assertNotIn("extra_content", canon["tool_calls"][1])
        again = normalize_tool_chat_messages([canon])
        self.assertEqual(
            again[0]["tool_calls"][0]["extra_content"]["google"]["thought_signature"],
            sig,
        )
        missing = canonical_assistant_tool_message("Applying.", [
            {"id": "c1", "name": "highlight_task",
             "arguments": {"task_name_or_id": "PS[228]"}},
            {"id": "c2", "name": "set_cursors",
             "arguments": {"timestamps": [1, 2]}},
        ])
        filled = ensure_gemini_thought_signatures([missing])
        self.assertEqual(
            filled[0]["tool_calls"][0]["extra_content"]["google"]["thought_signature"],
            GEMINI_SKIP_THOUGHT_SIGNATURE,
        )
        self.assertNotIn("extra_content", filled[0]["tool_calls"][1])
        self.assertTrue(needs_gemini_thought_signatures(
            base_url="https://generativelanguage.googleapis.com/v1beta/openai",
            preset="custom",
        ))
        self.assertTrue(needs_gemini_thought_signatures(preset="gemini"))
        self.assertFalse(needs_gemini_thought_signatures(
            base_url="http://127.0.0.1:11434/v1",
            model="gemini-2.5-flash",
            preset="ollama",
        ))

    def test_query_raw_metric_priority_episodes(self) -> None:
        from btf_viewer_pkg.parser import (  # noqa: WPS433
            BtfTrace,
            PriorityEpisode,
            TaskSegment,
            _task_merge_key,
        )

        mk = _task_merge_key("Low[266]")
        if mk == "Low[266]":
            mk = "\x00266\x00Low"
        ep = PriorityEpisode(
            mk=mk,
            task_label="Low[266]",
            base_pri=1,
            peak_pri=4,
            start_ns=3100000,
            stop_ns=3134000,
            inherited=True,
            inversion_suspect=True,
            medium_tasks=["Med[267]"],
            pattern="Mutex inherit L/M/H (Med[267])",
        )
        trace = BtfTrace(
            time_scale="us",
            tasks=["Low[266]", "Med[267]"],
            segments=[],
            sti_events=[],
            sti_channels=[],
            sti_events_by_target={},
            time_min=0,
            time_max=4000000,
            task_repr={mk: "Low[266]"},
            seg_map_by_merge_key={
                mk: [TaskSegment(task="Low[266]", start=3090000, end=3095000, core="Core_0")],
            },
            priority_episodes=[ep],
            priority_episodes_by_mk={mk: [ep]},
            has_priority_instrumentation=True,
        )
        out = query_raw_metric(trace, "Low[266]", "priority_inheritance")
        self.assertTrue(out["ok"])
        self.assertEqual(out["data"]["count"], 1)
        self.assertEqual(out["data"]["episodes"][0]["peak_pri"], 4)
        self.assertIn("Med[267]", out["data"]["episodes"][0]["medium_tasks"])
        scoped = query_raw_metric(
            trace, "266", "pi", lo=0, hi=1000)
        self.assertTrue(scoped["ok"])
        self.assertEqual(scoped["data"]["count"], 0)
        exec_out = query_raw_metric(trace, "Low[266]", "execution")
        self.assertEqual(exec_out["data"]["count"], 1)
        miss = query_raw_metric(trace, "NoSuch", "execution")
        self.assertFalse(miss["ok"])

    def test_build_ai_report_csv_and_html(self) -> None:
        csv_text = build_ai_report_csv(
            meta={"file": "demo.btf"},
            gui={"cursors": [10, 20], "view_mode": "task"},
            findings="1. [WARNING] Thrash",
            annotations=[{"time": 15, "note": "spike"}],
            conversation="You:\nhello\n",
        )
        self.assertIn("demo.btf", csv_text)
        self.assertIn("spike", csv_text)
        self.assertIn("Thrash", csv_text)
        html = build_ai_report_html(
            meta={"file": "demo.btf"},
            gui={"highlight": "Low[266]", "cursors": [10, 20]},
            findings="1. [WARNING] Thrash on Med[267]",
            annotations=[{"time": 1, "note": "n"}],
            conversation_html="<p>hi</p>",
            evidence_payload={
                "conclusion": "Med[267] off-CPU",
                "evidence": [
                    {"label": "off-CPU Med[267]", "time": 15},
                    {"label": "outside", "time": 99},
                ],
                "evidence_quality": {
                    "band": "medium",
                    "flags": {"direct_evidence": True},
                },
                "falsify": {"next_check": "Open preemption"},
            },
            analysis_complete=True,
        )
        self.assertIn("AI Diagnostic Report", html)
        self.assertIn("BTFViewer", html)
        self.assertIn('class="report-head"', html)
        self.assertIn('fill="#1C3A6E"', html)
        self.assertIn("Low[266]", html)
        self.assertIn("<p>hi</p>", html)
        self.assertIn("Executive summary", html)
        self.assertIn("Coverage summary", html)
        self.assertIn("Appendix", html)
        self.assertIn("Conversation export", html)
        self.assertIn("Rejected evidence", html)
        self.assertIn("In scope", html)
        self.assertIn("Excluded", html)
        self.assertIn('class="report-toc"', html)
        self.assertIn('data-toc="expand"', html)
        self.assertIn('data-toc="collapse"', html)
        self.assertIn("Expand all", html)
        self.assertIn("Collapse all", html)
        self.assertIn("<details class=\"report-card\"", html)
        self.assertIn('details.report-appendix', html)
        from btf_viewer_pkg.ai_tools import filter_entries_for_ai_report
        kept = filter_entries_for_ai_report([
            {"role": "assistant", "text": "ok",
             "tools": [{"name": "export_report", "status": "pending"}]},
            {"role": "user", "text": "why"},
        ])
        self.assertEqual(len(kept), 1)

    def test_tools_match_web(self) -> None:
        js = (BTF_ROOT / "web/src/utils/aiTools.js").read_text(encoding="utf-8")
        for name in AI_VIEWER_TOOL_NAMES:
            self.assertRegex(js, re.compile(rf"['\"]{re.escape(name)}['\"]"))
        self.assertIn("mermaid sequenceDiagram", AI_TOOL_SYSTEM_ADDENDUM)
        self.assertIn("mermaid sequenceDiagram", js)


if __name__ == "__main__":
    unittest.main()
