"""Time-aware core-affinity statistics (_task_core_affinity_rows)."""
from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path

BTF_ROOT = Path(__file__).resolve().parents[1]
if str(BTF_ROOT) not in sys.path:
    sys.path.insert(0, str(BTF_ROOT))

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from btf_viewer_pkg._bootstrap import install  # noqa: E402

install()

from PySide6.QtCore import Qt  # noqa: E402
from PySide6.QtWidgets import QApplication, QTableWidget  # noqa: E402

from btf_viewer_pkg.parser import (  # noqa: E402
    BtfTrace,
    StiEvent,
    TaskSegment,
    _affinity_mask_at_time,
    _format_affinity_mask_history,
    _task_core_affinity_rows,
    _task_merge_key,
)
from btf_viewer_pkg.stats import _StatsPanel  # noqa: E402


def _trace(sti, segs_by_label, cores=("Core_0", "Core_1", "Core_2", "Core_3")):
    seg_map = {}
    task_repr = {}
    for label, segs in segs_by_label.items():
        mk = _task_merge_key(label)
        task_repr[mk] = label
        seg_map[mk] = [
            TaskSegment(task=label, start=s, end=e, core=c) for s, e, c in segs
        ]
    return BtfTrace(
        time_scale="ns",
        tasks=list(seg_map.keys()),
        segments=[s for segs in seg_map.values() for s in segs],
        sti_events=sti,
        sti_channels=["task"],
        sti_events_by_target={"task": sti},
        time_min=0,
        time_max=1_000_000,
        seg_map_by_merge_key=seg_map,
        core_names=list(cores),
        task_repr=task_repr,
    )


class AffinityMaskHelpersTests(unittest.TestCase):
    def test_mask_at_time_before_first_is_none(self):
        hist = [(100, 0x1), (200, 0x8)]
        self.assertIsNone(_affinity_mask_at_time(hist, 50))
        self.assertEqual(_affinity_mask_at_time(hist, 100), 0x1)
        self.assertEqual(_affinity_mask_at_time(hist, 150), 0x1)
        self.assertEqual(_affinity_mask_at_time(hist, 200), 0x8)

    def test_format_mask_history_collapses_duplicates(self):
        self.assertEqual(_format_affinity_mask_history([(1, 1), (2, 1), (3, 8)]), "0x1 → 0x8")


class CoreAffinityRowsTests(unittest.TestCase):
    def test_static_mask_flags_true_violation(self):
        sti = [
            StiEvent(50, "Core_0", "task", "trigger", "affinity_set Pin[1] 0x1"),
        ]
        tr = _trace(sti, {
            "Pin[1]": [
                (100, 200, "Core_0"),
                (300, 400, "Core_2"),
            ],
        })
        rows = _task_core_affinity_rows(tr)
        self.assertEqual(len(rows), 1)
        label, mask, obs, viol = rows[0]
        self.assertEqual(label, "Pin[1]")
        self.assertEqual(mask, "0x1")
        self.assertIn("Core_0", obs)
        self.assertIn("Core_2", obs)
        self.assertEqual(viol, "Core_2")

    def test_interactive_rows_include_task_merge_key_on_request(self):
        sti = [
            StiEvent(50, "Core_0", "task", "trigger", "affinity_set Pin[1] 0x1"),
        ]
        tr = _trace(sti, {
            "Pin[1]": [(100, 200, "Core_0")],
        })
        rows = _task_core_affinity_rows(tr, include_merge_key=True)
        self.assertEqual(rows[0][0], _task_merge_key("Pin[1]"))
        self.assertEqual(rows[0][1:], ("Pin[1]", "0x1", "Core_0", "\u2014"))

    def test_pre_set_and_mask_change_not_false_violations(self):
        """AffM-style: free run, pin to core 0, then migrate to last core."""
        sti = [
            StiEvent(200, "Core_0", "task", "trigger", "affinity_set AffM[5] 0x1"),
            StiEvent(500, "Core_0", "task", "trigger", "affinity_set AffM[5] 0x8"),
        ]
        tr = _trace(sti, {
            "AffM[5]": [
                (50, 150, "Core_2"),       # before first set — unrestricted
                (250, 350, "Core_0"),      # under 0x1
                (450, 490, "Core_0"),      # still under 0x1 (ends before 0x8)
                (550, 650, "Core_3"),      # under 0x8
            ],
        })
        rows = _task_core_affinity_rows(tr)
        self.assertEqual(len(rows), 1)
        label, mask, obs, viol = rows[0]
        self.assertEqual(label, "AffM[5]")
        self.assertEqual(mask, "0x1 → 0x8")
        self.assertIn("Core_2", obs)
        self.assertEqual(viol, "\u2014")

    def test_violation_after_mask_change(self):
        sti = [
            StiEvent(100, "Core_0", "task", "trigger", "affinity_set AffM[5] 0x1"),
            StiEvent(300, "Core_0", "task", "trigger", "affinity_set AffM[5] 0x8"),
        ]
        tr = _trace(sti, {
            "AffM[5]": [
                (150, 200, "Core_0"),
                (350, 400, "Core_1"),  # not in 0x8
            ],
        })
        rows = _task_core_affinity_rows(tr)
        self.assertEqual(rows[0][3], "Core_1")


class CoreAffinityInteractionTests(unittest.TestCase):
    _app: QApplication | None = None

    @classmethod
    def setUpClass(cls) -> None:
        cls._app = QApplication.instance() or QApplication([])

    def test_row_hover_and_click_highlight_task(self):
        tr = _trace(
            [StiEvent(
                50, "Core_0", "task", "trigger",
                "affinity_set Pin[1] 0x1")],
            {"Pin[1]": [(100, 200, "Core_0")]},
        )
        panel = _StatsPanel()
        self.addCleanup(panel.deleteLater)
        panel._section_collapsed["affinity"] = False
        clicked = []
        panel.task_clicked.connect(clicked.append)
        panel.rebuild(tr)

        affinity = next(
            table for table in panel.findChildren(QTableWidget)
            if table.columnCount() == 4
            and table.horizontalHeaderItem(0) is not None
            and table.horizontalHeaderItem(0).text() == "Task"
            and table.horizontalHeaderItem(1).text() == "Mask"
        )
        self.assertTrue(hasattr(affinity, "_stats_row_hover_filter"))
        self.assertTrue(affinity.isSortingEnabled())
        self.assertTrue(affinity.horizontalHeader().sectionsClickable())
        self.assertEqual(
            affinity.selectionMode(),
            QTableWidget.SelectionMode.NoSelection)
        self.assertEqual(affinity.focusPolicy(), Qt.FocusPolicy.NoFocus)
        self.assertEqual(
            affinity.item(0, 0).data(Qt.ItemDataRole.UserRole),
            _task_merge_key("Pin[1]"))

        affinity.cellClicked.emit(0, 2)
        self.assertEqual(clicked, [_task_merge_key("Pin[1]")])


if __name__ == "__main__":
    unittest.main()
