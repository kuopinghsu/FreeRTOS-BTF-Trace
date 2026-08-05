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


if __name__ == "__main__":
    unittest.main()
