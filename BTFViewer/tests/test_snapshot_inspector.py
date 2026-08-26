"""CLI snapshot heatmap/chord after the three-column inspector refactor."""
from __future__ import annotations

import argparse
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
from PySide6.QtWidgets import QApplication, QHeaderView  # noqa: E402

from btf_viewer_pkg.cli import (  # noqa: E402
    _CLI_SNAPSHOT_TREE_COLS,
    _cli_snapshot_chord,
    _cli_snapshot_heatmap,
)
from btf_viewer_pkg.parser import _parse_btf  # noqa: E402

EXAMPLE_BTF = Path(__file__).resolve().parents[2] / "tracedata" / "example-8cores.btf.gz"
CLI_PY = (BTF_ROOT / "btf_viewer_pkg" / "cli.py").read_text(encoding="utf-8")


class TestSnapshotInspector(unittest.TestCase):
    _app: QApplication | None = None

    @classmethod
    def setUpClass(cls) -> None:
        cls._app = QApplication.instance() or QApplication([])

    def _args(self, **kw) -> argparse.Namespace:
        ns = argparse.Namespace(
            metric=None, task=None, lo=None, hi=None,
            width=1000, height=720, drill_row=None, drill_bin=None,
        )
        for k, v in kw.items():
            setattr(ns, k, v)
        return ns

    def test_cli_does_not_call_removed_sidebar_layout(self) -> None:
        self.assertNotIn("_apply_sidebar_layout", CLI_PY)
        self.assertIn("_cli_snapshot_fit_inspector_tree", CLI_PY)

    def test_chord_drill_row_shows_topology(self) -> None:
        if not EXAMPLE_BTF.is_file():
            self.skipTest(f"missing trace fixture: {EXAMPLE_BTF}")
        trace = _parse_btf(str(EXAMPLE_BTF))
        dlg, err = _cli_snapshot_chord(trace, self._args(drill_row=0))
        self.assertIsNone(err)
        self.assertIsNotNone(dlg)
        assert dlg is not None
        self.assertEqual(dlg._right_pane, "topology")
        self.assertIsNotNone(dlg._selected)
        self.assertEqual(dlg._tree.columnCount(), 8)
        self.assertEqual(
            [dlg._tree.headerItem().text(i) for i in range(8)],
            ["Core path", "Rate", "Count", "Ping",
             "Dwell", "Handoff", "Net", "Share"])
        hdr = dlg._tree.header()
        fm = hdr.fontMetrics()
        for col in range(1, _CLI_SNAPSHOT_TREE_COLS):
            text = dlg._tree.headerItem().text(col)
            extra = 16 if hdr.sortIndicatorSection() == col else 6
            self.assertLessEqual(
                fm.horizontalAdvance(text) + extra,
                dlg._tree.columnWidth(col),
                f"header {text!r} overflows column {col}")
        for col in range(8):
            self.assertEqual(
                dlg._tree.isColumnHidden(col),
                col >= _CLI_SNAPSHOT_TREE_COLS,
                f"snapshot should hide overflow column {col}")
        last_vis = _CLI_SNAPSHOT_TREE_COLS - 1
        last_x = (dlg._tree.header().sectionPosition(last_vis)
                  + dlg._tree.columnWidth(last_vis))
        self.assertLessEqual(
            last_x, dlg._tree.viewport().width(),
            "Core path / Rate / Count must stay inside the left pane")
        from PySide6.QtWidgets import QHeaderView
        for col in range(8):
            self.assertEqual(
                hdr.sectionResizeMode(col),
                QHeaderView.ResizeMode.Interactive)
        before = [dlg._tree.columnWidth(i) for i in range(8)]
        dlg._on_tree_header_clicked(2)
        after = [dlg._tree.columnWidth(i) for i in range(8)]
        self.assertEqual(before, after)
        self.assertEqual(
            dlg._tree.horizontalScrollBarPolicy(),
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scope_r = dlg._scope_combo.mapTo(dlg, dlg._scope_combo.rect().topRight())
        show_l = dlg._show_lbl.mapTo(dlg, dlg._show_lbl.rect().topLeft())
        self.assertGreaterEqual(
            show_l.x() - scope_r.x(), 6,
            "Analysis Scope combo overlaps the Show label")
        lbl_r = dlg._scope_lbl.mapTo(dlg, dlg._scope_lbl.rect().topRight())
        combo_l = dlg._scope_combo.mapTo(dlg, dlg._scope_combo.rect().topLeft())
        self.assertLessEqual(
            lbl_r.x(), combo_l.x(),
            "Analysis Scope label overlaps the combo")
        sizes = dlg._split.sizes()
        self.assertEqual(len(sizes), 3)
        self.assertGreater(sizes[1], sizes[0])
        self.assertGreater(sizes[1], sizes[2])
        self.assertAlmostEqual(sizes[0] / max(sizes[2], 1), 1.0, delta=0.35)
        self.assertEqual(dlg._ci_toolbar_scroll.height(), 22)
        combo = dlg._scope_combo
        combo.showPopup()
        self._app.processEvents()
        menu = combo._popup_menu
        self.assertIsNotNone(menu)
        self.assertTrue(bool(menu.windowFlags() & Qt.WindowType.Popup))
        self.assertGreater(menu.height(), 44)
        combo.hidePopup()
        dlg.close()
        self._app.processEvents()

    def test_heatmap_snapshot_shows_path_info(self) -> None:
        if not EXAMPLE_BTF.is_file():
            self.skipTest(f"missing trace fixture: {EXAMPLE_BTF}")
        trace = _parse_btf(str(EXAMPLE_BTF))
        dlg, err = _cli_snapshot_heatmap(trace, self._args())
        self.assertIsNone(err)
        self.assertIsNotNone(dlg)
        assert dlg is not None
        self.assertEqual(dlg._right_pane, "info")
        dlg.close()
        self._app.processEvents()


if __name__ == "__main__":
    unittest.main()
