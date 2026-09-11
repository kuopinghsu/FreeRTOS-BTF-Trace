"""Legend list and stats tables keep compact, consistent row heights."""
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

from PySide6.QtWidgets import QApplication, QTableWidget  # noqa: E402

from btf_viewer_pkg.config import (  # noqa: E402
    STATS_TABLE_HEADER_H,
    STATS_TABLE_ROW_H,
)
from btf_viewer_pkg.parser import _parse_btf  # noqa: E402
from btf_viewer_pkg.stats import _LegendWidget, _StatsPanel  # noqa: E402

EXAMPLE_BTF = Path(__file__).resolve().parents[2] / "tracedata" / "example-2cores.btf.gz"


class TestStatsLegendSpacing(unittest.TestCase):
    _app: QApplication | None = None

    @classmethod
    def setUpClass(cls) -> None:
        cls._app = QApplication.instance() or QApplication([])

    def test_enforce_stats_table_row_geometry_shrinks_platform_defaults(self) -> None:
        table = QTableWidget(5, 3)
        # Simulate Windows-ish default rows taller than the stats design size.
        for r in range(table.rowCount()):
            table.setRowHeight(r, 28)
        table.horizontalHeader().setFixedHeight(30)

        _StatsPanel._enforce_stats_table_row_geometry(table)

        self.assertEqual(table.horizontalHeader().height(), STATS_TABLE_HEADER_H)
        self.assertEqual(
            table.verticalHeader().defaultSectionSize(), STATS_TABLE_ROW_H)
        for r in range(table.rowCount()):
            self.assertEqual(table.rowHeight(r), STATS_TABLE_ROW_H)

    def test_legend_task_rows_use_compact_size_hint(self) -> None:
        if not EXAMPLE_BTF.is_file():
            self.skipTest(f"missing trace fixture: {EXAMPLE_BTF}")

        legend = _LegendWidget()
        legend.show()
        self._app.processEvents()

        trace = _parse_btf(str(EXAMPLE_BTF))
        legend.rebuild(trace)
        self._app.processEvents()

        self.assertEqual(legend._task_list.iconSize().width(), 14)
        self.assertEqual(legend._task_list.iconSize().height(), 14)
        self.assertGreater(legend._task_list.count(), 0)
        hint = legend._task_list.item(0).sizeHint()
        self.assertLessEqual(hint.height(), 22)
        self.assertGreaterEqual(hint.height(), 16)

        legend.close()
        self._app.processEvents()

    def test_legend_shows_empty_placeholder_when_filter_matches_nothing(self) -> None:
        # Web parity: LegendPanel.vue's `v-else class="legend-empty"` block —
        # a filter that hides every task must not leave a blank list.
        if not EXAMPLE_BTF.is_file():
            self.skipTest(f"missing trace fixture: {EXAMPLE_BTF}")

        legend = _LegendWidget()
        trace = _parse_btf(str(EXAMPLE_BTF))
        legend.rebuild(trace)
        self.assertIsNone(legend._empty_item)
        self.assertTrue(
            any(not it.isHidden() for it in legend._task_items.values()))

        legend._filter_tasks("no task name can possibly match this")
        self.assertIsNotNone(legend._empty_item)
        self.assertFalse(legend._empty_item.isHidden())
        self.assertTrue(
            all(it.isHidden() for it in legend._task_items.values()))

        legend._filter_tasks("")
        self.assertTrue(legend._empty_item.isHidden())
        self.assertTrue(
            any(not it.isHidden() for it in legend._task_items.values()))

        legend.close()
        self._app.processEvents()

    def test_legend_empty_placeholder_survives_rebuild(self) -> None:
        # rebuild() clears the QListWidget (deleting the C++ item); the stale
        # Python reference must be dropped, not reused after deletion.
        if not EXAMPLE_BTF.is_file():
            self.skipTest(f"missing trace fixture: {EXAMPLE_BTF}")

        legend = _LegendWidget()
        trace = _parse_btf(str(EXAMPLE_BTF))
        legend.rebuild(trace)
        legend._filter_tasks("no task name can possibly match this")
        self.assertIsNotNone(legend._empty_item)

        legend.rebuild(trace)  # clears the list; must not raise
        self.assertIsNone(legend._empty_item)
        self.assertTrue(
            any(not it.isHidden() for it in legend._task_items.values()))

        legend.close()
        self._app.processEvents()


if __name__ == "__main__":
    unittest.main()
