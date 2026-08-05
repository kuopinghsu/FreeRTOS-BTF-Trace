"""Distribution-chart dialog highlights the active metric tab."""
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

from PySide6.QtGui import QColor  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from btf_viewer_pkg.stats import (  # noqa: E402
    _MIG_PLOT_TABS,
    _PAIR_PLOT_TABS,
    _MetricsPlotDialog,
)

POINTS = [(1000 * i, 500 + 7 * i, None) for i in range(20)]


class TestPlotDialogTabs(unittest.TestCase):
    _app: QApplication | None = None

    @classmethod
    def setUpClass(cls) -> None:
        cls._app = QApplication.instance() or QApplication([])

    def _dialog(self, tabs, active_tab, switches: list) -> _MetricsPlotDialog:
        dlg = _MetricsPlotDialog(
            "Dwell",
            POINTS,
            "us",
            QColor("#4CAF50"),
            on_point_click=lambda *_a: None,
            is_dark=False,
            scope_scoped=False,
            scope_badge="FULL TRACE",
            scope_detail="whole trace",
            tabs=tabs,
            active_tab=active_tab,
            on_tab_change=switches.append,
        )
        self.addCleanup(dlg.deleteLater)
        return dlg

    def _checked(self, dlg: _MetricsPlotDialog) -> list[str]:
        return [k for k, b in dlg._tab_buttons.items() if b.isChecked()]

    def test_active_tab_is_the_only_checked_button(self) -> None:
        dlg = self._dialog(_MIG_PLOT_TABS, "mig_dwell", [])
        self.assertEqual(list(dlg._tab_buttons), [k for k, _ in _MIG_PLOT_TABS])
        self.assertEqual(self._checked(dlg), ["mig_dwell"])
        self.assertEqual(dlg.active_tab(), "mig_dwell")

    def test_clicking_a_tab_moves_the_highlight_and_notifies(self) -> None:
        switches: list[str] = []
        dlg = self._dialog(_MIG_PLOT_TABS, "mig_dwell", switches)
        dlg._tab_buttons["mig_rate"].click()
        self.assertEqual(switches, ["mig_rate"])
        self.assertEqual(self._checked(dlg), ["mig_rate"])

    def test_set_active_tab_restores_the_highlight(self) -> None:
        dlg = self._dialog(_PAIR_PLOT_TABS, "pair_gap", [])
        dlg._tab_buttons["pair_rate"].click()
        self.assertEqual(self._checked(dlg), ["pair_rate"])
        # A rejected switch (no samples for that tab) must not leave the
        # clicked tab highlighted.
        dlg.set_active_tab("pair_gap")
        self.assertEqual(self._checked(dlg), ["pair_gap"])
        self.assertEqual(dlg.active_tab(), "pair_gap")

    def test_checked_tab_uses_the_accent_style(self) -> None:
        dlg = self._dialog(_MIG_PLOT_TABS, "mig_dwell", [])
        ss = dlg._tab_buttons["mig_dwell"].styleSheet()
        self.assertIn("QPushButton#plot_tab:checked", ss)
        self.assertIn("#1976D2", ss)

    def test_no_tab_row_without_tabs(self) -> None:
        dlg = self._dialog(None, None, [])
        self.assertEqual(dlg._tab_buttons, {})


if __name__ == "__main__":
    unittest.main()
