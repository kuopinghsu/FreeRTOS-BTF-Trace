"""``Task-N`` aliasing for the Export dialog's Anonymize option.

Parity with ``web/tests/anonymizeExport.test.js``.
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

BTF_ROOT = Path(__file__).resolve().parents[1]
if str(BTF_ROOT) not in sys.path:
    sys.path.insert(0, str(BTF_ROOT))

from btf_viewer_pkg.anonymize_export import (  # noqa: E402
    ANON_PREFIX,
    anonymize_btf_text,
    anonymize_json_strings,
    anonymize_with_map,
    build_task_alias_map,
)

_NAMES = ["ControlTask", "IdleHook", "ControlTaskHelper", "Sensor"]


class BuildMapTests(unittest.TestCase):
    def test_sorted_stable_numbering(self):
        m = build_task_alias_map(_NAMES)
        self.assertEqual(m, {
            "ControlTask": "Task-1",
            "ControlTaskHelper": "Task-2",
            "IdleHook": "Task-3",
            "Sensor": "Task-4",
        })

    def test_dedupes_and_trims_blanks(self):
        self.assertEqual(
            build_task_alias_map(["  A ", "A", "", None, "B"]),
            {"A": "Task-1", "B": "Task-2"})


class SubstitutionTests(unittest.TestCase):
    def setUp(self):
        self.m = build_task_alias_map(_NAMES)

    def test_whole_token_only(self):
        # "ControlTask" must not be replaced inside "ControlTaskHelper".
        out = anonymize_with_map("ControlTaskHelper ran after ControlTask", self.m)
        self.assertEqual(out, "Task-2 ran after Task-1")

    def test_btf_csv_line(self):
        line = "1000,Core_0,0,T,ControlTask,0,resume,\n2000,Core_0,0,T,Sensor,0,preempt,"
        out = anonymize_btf_text(line, self.m)
        self.assertIn(",T,Task-1,0,resume,", out)
        self.assertIn(",T,Task-4,0,preempt,", out)
        self.assertNotIn("ControlTask", out)

    def test_json_strings_recursive(self):
        obj = {
            "title": "ControlTask misses deadline",
            "rows": [{"label": "Sensor", "n": 3}],
            "nested": {"note": "see IdleHook"},
            "keep_number": 42,
        }
        out = anonymize_json_strings(obj, self.m)
        self.assertEqual(out["title"], "Task-1 misses deadline")
        self.assertEqual(out["rows"][0]["label"], "Task-4")
        self.assertEqual(out["rows"][0]["n"], 3)
        self.assertEqual(out["nested"]["note"], "see Task-3")
        self.assertEqual(out["keep_number"], 42)

    def test_empty_and_no_map_passthrough(self):
        self.assertEqual(anonymize_with_map("ControlTask", {}), "ControlTask")
        self.assertEqual(anonymize_with_map("", self.m), "")
        self.assertEqual(anonymize_with_map(None, self.m), "")


class ParityTests(unittest.TestCase):
    def test_module_and_js_in_step(self):
        py = (BTF_ROOT / "btf_viewer_pkg" / "anonymize_export.py").read_text("utf-8")
        js = (BTF_ROOT / "web" / "src" / "utils" / "anonymizeExport.js").read_text("utf-8")
        for py_name, js_name in (
            ("def build_task_alias_map", "export function buildTaskAliasMap"),
            ("def anonymize_with_map", "export function anonymizeWithMap"),
            ("def anonymize_json_strings", "export function anonymizeJsonStrings"),
            ("anonymize_btf_text = anonymize_with_map",
             "export const anonymizeBtfText = anonymizeWithMap"),
            ('ANON_PREFIX = "Task-"', "export const ANON_PREFIX = 'Task-'"),
        ):
            self.assertIn(py_name, py, py_name)
            self.assertIn(js_name, js, js_name)


if __name__ == "__main__":
    unittest.main()
