"""AI response flow helpers (btf_viewer_pkg/ai_response_flow.py).

Mirrors web/tests/aiResponseFlow.test.js.
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

BTF_ROOT = Path(__file__).resolve().parents[1]
if str(BTF_ROOT) not in sys.path:
    sys.path.insert(0, str(BTF_ROOT))

from btf_viewer_pkg.ai_response_flow import (  # noqa: E402
    format_analysis_status,
    format_elapsed_seconds,
    format_tool_usage_summary_line,
    plan_query_blocks,
    tool_usage_from_chat_tools,
)

_ZH = {"analysis_completed": "分析完成", "time_used": "用時", "seconds_unit": "秒"}


class ResponseFlowTests(unittest.TestCase):
    def test_elapsed_one_decimal(self) -> None:
        self.assertEqual(format_elapsed_seconds(28.268), "28.3")
        self.assertEqual(format_elapsed_seconds(1.84), "1.8")
        self.assertEqual(format_elapsed_seconds(0), "0.0")
        self.assertEqual(format_elapsed_seconds("bad"), "0.0")

    def test_analysis_status_per_language(self) -> None:
        self.assertEqual(format_analysis_status(28.3, {}), "Analysis completed · 28.3 s")
        self.assertEqual(format_analysis_status(10.14, _ZH), "分析完成 · 用時 10.1 秒")

    def test_chat_tool_rollup_counts_agree(self) -> None:
        tools = [
            {"name": "query_raw_metric", "status": "applied", "result": "Max off-CPU 34.9 ms"},
            {"name": "query_raw_metric", "status": "applied", "result": ""},
            {"name": "query_raw_metric", "status": "failed", "result": "no data"},
            {"name": "verify_claim", "status": "applied", "result": "inconclusive"},
        ]
        s = tool_usage_from_chat_tools(tools)
        self.assertEqual(s["total"], 4)
        self.assertEqual(s["unique"], 2)
        self.assertEqual(s["failed"], 1)
        self.assertEqual(s["groups"][0]["name"], "query_raw_metric")
        self.assertEqual(s["groups"][0]["count"], 3)
        self.assertEqual(
            format_tool_usage_summary_line(tools, {}),
            "Tool usage · 4 calls / 2 tools · 1 failed",
        )
        self.assertEqual(sum(g["count"] for g in s["groups"]), s["total"])

    def test_completed_query_collapses_hiding_narration(self) -> None:
        msgs = [
            {"role": "user", "text": "Why the spike?",
             "turn_complete": True, "analysis_elapsed_s": 10.1},
            {"role": "assistant", "text": "I will query the trace.",
             "tools": [{"name": "query_raw_metric", "status": "applied"}], "batch_id": "b1"},
            {"role": "assistant", "text": "Let me verify this.",
             "tools": [{"name": "verify_claim", "status": "applied"}], "batch_id": "b2"},
            {"role": "assistant", "text": "The spike aligns with an off-CPU interval."},
        ]
        hidden, meta = plan_query_blocks(msgs)
        self.assertEqual(sorted(hidden), [1, 2])
        self.assertIn(3, meta)
        self.assertEqual(meta[3]["elapsed_s"], 10.1)
        self.assertEqual(len(meta[3]["tools"]), 2)
        self.assertEqual(meta[3]["batch_ids"], ["b1", "b2"])

    def test_per_round_tool_only_turns_hidden_even_while_running(self) -> None:
        msgs = [
            {"role": "user", "text": "q"},
            {"role": "assistant", "text": "",
             "tools": [{"name": "set_cursors", "status": "pending"}], "batch_id": "b1"},
            {"role": "assistant", "text": "Working on it…"},
        ]
        hidden, meta = plan_query_blocks(msgs)
        self.assertEqual(sorted(hidden), [1])
        self.assertNotIn(2, hidden)
        self.assertEqual(meta, {})

    def test_no_answer_hosts_block_on_last_tool_turn(self) -> None:
        msgs = [
            {"role": "user", "text": "q", "turn_complete": True, "analysis_elapsed_s": 3},
            {"role": "assistant", "text": "",
             "tools": [{"name": "query_raw_metric", "status": "applied"}], "batch_id": "b1"},
        ]
        hidden, meta = plan_query_blocks(msgs)
        self.assertEqual(hidden, set())
        self.assertIn(1, meta)

    def test_evidence_panel_entry_is_never_hidden(self) -> None:
        # Regression: only assistant turns collapse — the Evidence & Validation
        # panel (role 'evidence') and other non-assistant entries stay.
        msgs = [
            {"role": "user", "text": "q", "turn_complete": True, "analysis_elapsed_s": 5},
            {"role": "assistant", "text": "I will query.",
             "tools": [{"name": "query_raw_metric", "status": "applied"}], "batch_id": "b1"},
            {"role": "assistant", "text": "The answer."},
            {"role": "evidence", "text": "**Verdict:** Correlated"},
        ]
        hidden, meta = plan_query_blocks(msgs)
        self.assertEqual(sorted(hidden), [1])          # only the narration turn
        self.assertIn(2, meta)                          # answer hosts the block
        self.assertNotIn(3, hidden)                     # evidence panel kept

    def test_zero_tool_completed_query(self) -> None:
        msgs = [
            {"role": "user", "text": "q", "turn_complete": True, "analysis_elapsed_s": 1.8},
            {"role": "assistant", "text": "Short answer."},
        ]
        _hidden, meta = plan_query_blocks(msgs)
        self.assertEqual(len(meta[1]["tools"]), 0)


if __name__ == "__main__":
    unittest.main()
