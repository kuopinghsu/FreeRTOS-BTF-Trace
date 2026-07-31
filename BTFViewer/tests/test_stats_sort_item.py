"""Unit tests for _StatsSortItem, the comparator backing click-to-sort stats tables."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

BTF_ROOT = Path(__file__).resolve().parents[1]
if str(BTF_ROOT) not in sys.path:
    sys.path.insert(0, str(BTF_ROOT))

import tests  # noqa: F401,E402 — applies QT_QPA_PLATFORM=offscreen

from btf_viewer_pkg.stats import _StatsSortItem  # noqa: E402

class StatsSortItemTests(unittest.TestCase):
    def test_numeric_sort_key_orders_by_value_not_text(self) -> None:
        items = [_StatsSortItem("9%", 9), _StatsSortItem("10%", 10), _StatsSortItem("2%", 2)]
        ordered = sorted(items)
        self.assertEqual([str(i.text()) for i in ordered], ["2%", "9%", "10%"])

    def test_string_sort_key_is_case_insensitive(self) -> None:
        items = [_StatsSortItem("Task_B", "task_b"), _StatsSortItem("task_a", "task_a")]
        ordered = sorted(items)
        self.assertEqual([str(i.text()) for i in ordered], ["task_a", "Task_B"])

    def test_default_sort_key_falls_back_to_lowercased_text(self) -> None:
        a = _StatsSortItem("Core_1")
        b = _StatsSortItem("core_2")
        self.assertLess(a, b)

    def test_mixed_numeric_and_string_keys_fall_back_to_string_compare(self) -> None:
        # A numeric key compared against a non-numeric key must not raise —
        # both sides fall back to a lowercased-string comparison.
        a = _StatsSortItem("5", 5)
        b = _StatsSortItem("dash", "\u2014")
        self.assertLess(a, b)  # "5" < "\u2014" lexicographically

if __name__ == "__main__":
    unittest.main()
