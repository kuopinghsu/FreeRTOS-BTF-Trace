"""Unit tests for Core-Pair Gap/Rate plot point builders."""
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

from btf_viewer_pkg.stats import _MetricsPlotDialog  # noqa: E402
from btf_viewer_pkg.parser import (  # noqa: E402
    BtfTrace,
    MigrationEvent,
    _PAIR_BOUNCE_POINT_COLOR,
    _pair_gap_plot_points,
    _pair_plot_key,
    _pair_rate_plot_points,
    _parse_pair_plot_key,
)


def _trace_with_pair_migs(migs, bounce_ns=()):
    return BtfTrace(
        time_scale="us",
        tasks=[],
        segments=[],
        sti_events=[],
        sti_channels=[],
        sti_events_by_target={},
        time_min=0,
        time_max=10_000,
        core_names=["Core_0", "Core_1", "Core_2"],
        migrations=list(migs),
        lock_bounce_migration_ns=frozenset(bounce_ns),
    )


class PairPlotKeyTests(unittest.TestCase):
    def test_round_trip(self) -> None:
        key = _pair_plot_key("Core_5", "Core_7")
        self.assertEqual(_parse_pair_plot_key(key), ("Core_5", "Core_7"))

    def test_invalid(self) -> None:
        self.assertIsNone(_parse_pair_plot_key(""))
        self.assertIsNone(_parse_pair_plot_key("Core_0"))


class PairGapPlotTests(unittest.TestCase):
    def test_gap_points_and_bounce_color(self) -> None:
        migs = [
            MigrationEvent(100, "T:1", "Core_0", "Core_1", gap_ns=10),
            MigrationEvent(200, "T:1", "Core_0", "Core_1", gap_ns=30),
            MigrationEvent(300, "T:2", "Core_1", "Core_0", gap_ns=50),  # other pair
            MigrationEvent(400, "T:1", "Core_0", "Core_1", gap_ns=0),   # skipped
        ]
        tr = _trace_with_pair_migs(migs, bounce_ns=(200,))
        pts = _pair_gap_plot_points(tr, "Core_0", "Core_1")
        self.assertEqual(len(pts), 2)
        self.assertEqual(pts[0][:3], (100, 10, migs[0]))
        self.assertEqual(len(pts[0]), 3)  # no bounce accent
        self.assertEqual(pts[1][0], 200)
        self.assertEqual(pts[1][1], 30)
        self.assertEqual(pts[1][3], _PAIR_BOUNCE_POINT_COLOR)

    def test_scope_filter(self) -> None:
        migs = [
            MigrationEvent(100, "T:1", "Core_0", "Core_1", gap_ns=10),
            MigrationEvent(200, "T:1", "Core_0", "Core_1", gap_ns=20),
            MigrationEvent(300, "T:1", "Core_0", "Core_1", gap_ns=30),
        ]
        tr = _trace_with_pair_migs(migs)
        pts = _pair_gap_plot_points(tr, "Core_0", "Core_1", lo=150, hi=250)
        self.assertEqual([p[0] for p in pts], [200])


class PairRatePlotTests(unittest.TestCase):
    def test_rate_uses_previous_on_same_pair(self) -> None:
        migs = [
            MigrationEvent(100, "T:1", "Core_0", "Core_1", gap_ns=1),
            MigrationEvent(150, "T:1", "Core_1", "Core_0", gap_ns=1),  # other dir
            MigrationEvent(250, "T:1", "Core_0", "Core_1", gap_ns=1),
            MigrationEvent(400, "T:1", "Core_0", "Core_1", gap_ns=1),
        ]
        tr = _trace_with_pair_migs(migs, bounce_ns=(400,))
        pts = _pair_rate_plot_points(tr, "Core_0", "Core_1")
        # gaps: 250-100=150, 400-250=150
        self.assertEqual([(p[0], p[1]) for p in pts], [(250, 150), (400, 150)])
        self.assertEqual(pts[1][3], _PAIR_BOUNCE_POINT_COLOR)


class PairPlotDialogButtonTests(unittest.TestCase):
    """clicked(bool) must not leak `checked` into the pair callbacks."""

    _app: QApplication | None = None

    @classmethod
    def setUpClass(cls) -> None:
        cls._app = QApplication.instance() or QApplication([])

    def test_footer_buttons_call_callbacks_without_checked_arg(self) -> None:
        calls: list[tuple] = []
        from_core, to_core, prefer_bounce = "Core_5", "Core_7", True
        dlg = _MetricsPlotDialog(
            "Core_5 → Core_7",
            [(100, 10, None)],
            "us",
            QColor("#4CAF50"),
            on_point_click=lambda *_a: None,
            is_dark=False,
            scope_scoped=False,
            scope_badge="",
            scope_detail="",
            on_open_heatmap=(lambda f=from_core, t=to_core, b=prefer_bounce:
                             calls.append(("heatmap", f, t, b))),
            on_open_chord=(lambda f=from_core, t=to_core, b=prefer_bounce:
                           calls.append(("chord", f, t, b))),
        )
        self.addCleanup(dlg.deleteLater)

        self.assertIsNotNone(dlg._btn_open_heatmap)
        self.assertIsNotNone(dlg._btn_open_chord)
        dlg._btn_open_heatmap.click()
        dlg._btn_open_chord.click()

        self.assertEqual(calls, [
            ("heatmap", "Core_5", "Core_7", True),
            ("chord", "Core_5", "Core_7", True),
        ])

    def test_footer_buttons_absent_without_callbacks(self) -> None:
        dlg = _MetricsPlotDialog(
            "Exec",
            [(100, 10, None)],
            "us",
            QColor("#4CAF50"),
            on_point_click=lambda *_a: None,
            is_dark=False,
            scope_scoped=False,
            scope_badge="",
            scope_detail="",
        )
        self.addCleanup(dlg.deleteLater)
        self.assertIsNone(dlg._btn_open_heatmap)
        self.assertIsNone(dlg._btn_open_chord)


if __name__ == "__main__":
    unittest.main()
