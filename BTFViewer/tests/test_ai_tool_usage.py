"""Authoritative AI tool-usage record (btf_viewer_pkg/ai_tool_usage.py)."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

BTF_ROOT = Path(__file__).resolve().parents[1]
if str(BTF_ROOT) not in sys.path:
    sys.path.insert(0, str(BTF_ROOT))

from btf_viewer_pkg.ai_tool_usage import (  # noqa: E402
    AI_TOOL_USAGE_CATEGORIES,
    ai_tool_usage_category,
    is_trace_query_tool,
    record_tool_usage,
    seed_tool_usage,
    summarize_tool_usage,
    tool_brief_result,
)


class ToolUsageTests(unittest.TestCase):
    def test_category_set_is_stable(self) -> None:
        self.assertEqual(
            AI_TOOL_USAGE_CATEGORIES,
            ("Evidence", "Analysis", "Verification", "Viewer"),
        )
        self.assertEqual(ai_tool_usage_category("query_raw_metric"), "Evidence")
        self.assertEqual(ai_tool_usage_category("search_timeline"), "Evidence")
        self.assertEqual(ai_tool_usage_category("correlate_events"), "Analysis")
        self.assertEqual(ai_tool_usage_category("verify_claim"), "Verification")
        self.assertEqual(ai_tool_usage_category("set_cursors"), "Viewer")
        self.assertEqual(ai_tool_usage_category("mystery_tool"), "Analysis")

    def test_trace_query_is_evidence_category(self) -> None:
        self.assertTrue(is_trace_query_tool("query_raw_metric"))
        self.assertFalse(is_trace_query_tool("correlate_events"))
        self.assertFalse(is_trace_query_tool("set_cursors"))

    def test_empty_summary(self) -> None:
        s = summarize_tool_usage({"calls": []})
        self.assertEqual(s["total"], 0)
        self.assertEqual(s["unique"], 0)
        self.assertEqual(s["trace_queries"], 0)
        self.assertEqual(s["groups"], [])

    def test_one_call_brief(self) -> None:
        u = record_tool_usage(
            {"calls": []},
            name="query_raw_metric",
            result={"ok": True, "data": {
                "metric": "off_cpu", "id": 267, "stat": "Max",
                "value": 34.924, "unit": " ms",
            }},
        )
        s = summarize_tool_usage(u)
        self.assertEqual(s["total"], 1)
        self.assertEqual(s["groups"][0]["brief"], "Found off_cpu[267] Max = 34.924 ms")

    def test_repeated_calls_grouped(self) -> None:
        u = {"calls": []}
        for _ in range(3):
            u = record_tool_usage(u, name="query_raw_metric", result={"ok": True})
        u = record_tool_usage(u, name="search_timeline", result={"ok": True})
        s = summarize_tool_usage(u)
        self.assertEqual(s["total"], 4)
        self.assertEqual(s["unique"], 2)
        self.assertEqual(s["groups"][0]["count"], 3)
        self.assertEqual(s["groups"][1]["count"], 1)

    def test_failed_calls_and_categories(self) -> None:
        u = {"calls": []}
        u = record_tool_usage(u, name="query_raw_metric", result={"ok": True})
        u = record_tool_usage(u, name="query_raw_metric", result={"ok": False, "error": "no data"})
        u = record_tool_usage(u, name="correlate_events", result={"ok": True})
        u = record_tool_usage(u, name="verify_claim", result={"ok": True, "data": {"verdict": "inconclusive"}})
        u = record_tool_usage(u, name="set_cursors", result={"ok": True})
        s = summarize_tool_usage(u)
        self.assertEqual(s["ok"], 4)
        self.assertEqual(s["failed"], 1)
        self.assertEqual(s["trace_queries"], 2)
        self.assertEqual(
            s["by_category"],
            {"Evidence": 2, "Analysis": 1, "Verification": 1, "Viewer": 1},
        )

    def test_seed_from_names(self) -> None:
        s = summarize_tool_usage(seed_tool_usage(
            ["query_raw_metric", "verify_claim", {"name": "set_cursors"}]))
        self.assertEqual(s["total"], 3)
        self.assertEqual(s["failed"], 0)

    def test_brief_never_invents_text(self) -> None:
        self.assertEqual(
            tool_brief_result("verify_claim", {"data": {
                "verdict": "inconclusive",
                "reason": "mutex ownership was not established",
            }}),
            "Inconclusive — mutex ownership was not established",
        )
        self.assertEqual(tool_brief_result("set_cursors", {"ok": True}), "")
        self.assertEqual(tool_brief_result("correlate_events", {"ok": True, "message": "ok"}), "")


if __name__ == "__main__":
    unittest.main()
