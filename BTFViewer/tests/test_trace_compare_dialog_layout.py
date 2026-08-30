"""Desktop Trace Compare: the few-column tables (Summary, Core Util, Response,
…) divide the full page width — no dead strip to the right of the last column,
whatever the Δ values are.  The 16-column Migrations table keeps content-width
columns and scrolls horizontally instead.
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

BTF_ROOT = Path(__file__).resolve().parents[1]
if str(BTF_ROOT) not in sys.path:
    sys.path.insert(0, str(BTF_ROOT))
if str(BTF_ROOT / "tests") not in sys.path:
    sys.path.insert(0, str(BTF_ROOT / "tests"))

import tests  # noqa: F401,E402 — applies QT_QPA_PLATFORM=offscreen

from PySide6.QtWidgets import QApplication  # noqa: E402
from PySide6.QtWidgets import QHeaderView  # noqa: E402

from btf_viewer_pkg.stats import _TraceCompareDialog  # noqa: E402
from test_trace_compare import _mini_trace  # noqa: E402


class _Scene:
    def cursor_times(self):
        return []


class _View:
    _scene = _Scene()


class _Tab:
    def __init__(self, trace, path):
        self.trace = trace
        self.path = path
        self.view = _View()


class _FakeWin:
    _ai_enabled = False
    _stats_panel = None

    def __init__(self, tabs):
        self._tabs = tabs

    def _ai_read_settings(self):
        return {}


class TraceCompareColumnFitTest(unittest.TestCase):
    def _dialog(self):
        if QApplication.instance() is None:
            QApplication([])
        tr_ful = _mini_trace(
            {"A[1]": [(0, 100, "Core_0"), (200, 350, "Core_1")],
             "B[2]": [(50, 150, "Core_2")]},
            ticks=(1000, 2000, 3000), time_max=20000)
        tr_less = _mini_trace(
            {"A[1]": [(0, 60, "Core_0"), (120, 300, "Core_3")],
             "C[3]": [(10, 400, "Core_5")]},
            ticks=(), time_max=20000)
        dlg = _TraceCompareDialog(
            win=_FakeWin([_Tab(tr_ful, "tickful.btf"), _Tab(tr_less, "tickless.btf")]))
        self.addCleanup(dlg.deleteLater)
        return dlg

    def test_narrow_tables_stretch_columns_wide_table_does_not(self):
        dlg = self._dialog()
        self.assertEqual(
            dlg._summary_table.horizontalHeader().sectionResizeMode(0),
            QHeaderView.ResizeMode.Stretch)
        self.assertTrue(dlg._mig_table.property("compareWideTable"))
        self.assertEqual(
            dlg._mig_table.horizontalHeader().sectionResizeMode(0),
            QHeaderView.ResizeMode.Interactive)

    def test_summary_columns_divide_the_full_width(self):
        dlg = self._dialog()
        dlg.resize(1200, 950)
        dlg.show()
        app = QApplication.instance()
        app.processEvents()
        dlg._combo_a.setCurrentIndex(0)
        for bi in (0, 1, 0):                     # identical, different, back
            dlg._combo_b.setCurrentIndex(bi)
            app.processEvents()
            t = dlg._summary_table
            widths = [t.columnWidth(i) for i in range(t.columnCount())]
            vp_w = dlg._pages.widget(0).viewport().width()
            # All columns together span the viewport (flush right edge) and none
            # is starved so another can absorb the slack.
            self.assertAlmostEqual(sum(widths), vp_w, delta=6)
            self.assertGreater(min(widths), vp_w // len(widths) - 40)
        dlg.close()
        app.processEvents()


if __name__ == "__main__":
    unittest.main()
