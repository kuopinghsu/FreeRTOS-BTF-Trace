"""Export ▸ Anonymize actually rewrites the embedded / sliced ``.btf`` text.

Regression: the desktop alias map was keyed on the decorated display name
(``Runner[1]``) which never matches the raw BTF token (``[0/0001]Runner``), so
the embedded trace kept its real task names.  It must key on the **bare** name,
same as the web ``exportTaskAliasMap`` / ``buildExportAnonymizer``.
"""
from __future__ import annotations

import sys
import types
import unittest
from pathlib import Path

BTF_ROOT = Path(__file__).resolve().parents[1]
if str(BTF_ROOT) not in sys.path:
    sys.path.insert(0, str(BTF_ROOT))

from btf_viewer_pkg._bootstrap import install  # noqa: E402

install()

from btf_viewer_pkg.mainwindow import MainWindow  # noqa: E402
from btf_viewer_pkg.anonymize_export import anonymize_btf_text  # noqa: E402

APP = (BTF_ROOT / "web" / "src" / "App.vue").read_text("utf-8")
SP = (BTF_ROOT / "web" / "src" / "components" / "StatisticsPanel.vue").read_text("utf-8")
MW = (BTF_ROOT / "btf_viewer_pkg" / "mainwindow.py").read_text("utf-8")

# task_repr holds decorated raw reprs; the alias map must reduce them to bare
# names (Runner, Worker, CS) — IDLE / TICK excluded.
_TASK_REPR = {
    "k1": "[0/0001]Runner",
    "k2": "Worker[7]",
    "k3": "Sensor(0x9)",
    "k4": "[1/0002]IDLE0",
    "k5": "TICK",
}


class AliasMapKeysBareNamesTests(unittest.TestCase):
    def _map(self):
        fake = types.SimpleNamespace(_trace=types.SimpleNamespace(task_repr=_TASK_REPR))
        return MainWindow._export_task_alias_map(fake)

    def test_keys_are_bare_names_sorted(self):
        self.assertEqual(self._map(), {
            "Runner": "Task-1", "Sensor": "Task-2", "Worker": "Task-3",
        })

    def test_rewrites_the_raw_btf_token_forms(self):
        amap = self._map()
        line = (
            "1013196,Core_0,0,T,[0/0001]Runner,0,preempt,create pri:4\n"
            "1013200,Core_0,0,T,Worker[7],0,resume,\n"
            "1013300,Core_0,0,T,[1/0002]IDLE0,0,preempt,\n"
        )
        out = anonymize_btf_text(line, amap)
        self.assertIn("[0/0001]Task-1,", out)   # name gone, ids kept
        self.assertIn("Task-3[7]", out)
        self.assertIn("IDLE0", out)             # idle untouched
        self.assertNotIn("Runner", out)
        self.assertNotIn("Worker", out)


class WebParityTests(unittest.TestCase):
    def test_both_sides_key_on_the_bare_task_name(self):
        self.assertIn("_parse_task_name(str(raw))[2]", MW)   # desktop
        self.assertIn("parseTaskName(String(raw))", APP)     # web exportTaskAliasMap
        self.assertIn("parseTaskName(String(raw))", SP)      # web buildExportAnonymizer


if __name__ == "__main__":
    unittest.main()
