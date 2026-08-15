"""Statistics variability metrics: jitter and population standard deviation."""
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
    _HistogramWidget,
    _ScatterWidget,
    _StatsPanel,
    _hist_bar_tip_lines,
    _hist_build_model,
    _hist_summarize,
)
from btf_viewer_pkg.timeline_util import _format_time  # noqa: E402


class TestStatsVariability(unittest.TestCase):
    _app: QApplication | None = None

    @classmethod
    def setUpClass(cls) -> None:
        cls._app = QApplication.instance() or QApplication([])

    def test_live_summary_jitter_and_population_stddev(self) -> None:
        summary = _StatsPanel._summarize_samples(None, [10, 20, 30], "ns")
        self.assertIsNotNone(summary)
        mn, avg, mx, jitter, stddev, p95, p99 = summary

        self.assertEqual(mn, _format_time(10, "ns"))
        self.assertEqual(avg, _format_time(20, "ns"))
        self.assertEqual(mx, _format_time(30, "ns"))
        self.assertEqual(jitter, _format_time(20, "ns"))
        self.assertEqual(stddev, _format_time(8, "ns"))
        self.assertEqual(p95, _format_time(30, "ns"))
        self.assertEqual(p99, _format_time(30, "ns"))

    def test_export_summary_includes_variability(self) -> None:
        summary = _StatsPanel._summarize_samples_export(
            None, [10, 20, 30], "ns"
        )
        self.assertIsNotNone(summary)
        mn, avg, trim, mx, jitter, stddev, p50, p95 = summary

        self.assertEqual((mn, avg, trim, mx), tuple(
            _format_time(v, "ns") for v in (10, 20, 20, 30)
        ))
        self.assertEqual(jitter, _format_time(20, "ns"))
        self.assertEqual(stddev, _format_time(8, "ns"))
        self.assertEqual(p50, _format_time(20, "ns"))
        self.assertEqual(p95, _format_time(30, "ns"))

    def test_single_sample_jitter_and_stddev_are_zero(self) -> None:
        summary = _StatsPanel._summarize_samples(None, [42], "ns")
        self.assertIsNotNone(summary)
        _mn, _avg, _mx, jitter, stddev, _p95, _p99 = summary
        zero = _format_time(0, "ns")
        self.assertEqual(jitter, zero)
        self.assertEqual(stddev, zero)

    def test_findings_still_read_max_after_variability_columns(self) -> None:
        """Export rows keep Max at fixed indices used by analysis findings."""
        from btf_viewer_pkg.stats import _build_workflow_analysis_findings

        findings = _build_workflow_analysis_findings(
            core_rows=[("Core_0", 50.0), ("Core_1", 50.0)],
            exec_rows=[
                ("mk1", "Worker", 100, 40.0, "1us", "2us", "2us", "10us",
                 "9us", "3us", "2us", "8us"),
            ],
            block_rows=[
                ("mk1", "Worker", 50, "1us", "2us", "2us", "20us",
                 "19us", "4us", "2us", "8us"),
            ],
            mig_rows=[],
            pair_rows=[],
            priority_rows=[],
            sync_rows=[],
            sync_issues=[],
            tick={"tick_count": 0},
            time_scale="us",
        )
        exec_text = next(
            f["text"] for f in findings
            if f["title"].startswith("Top tasks by CPU")
        )
        block_text = next(
            f["text"] for f in findings
            if "Blocking" in f["title"]
        )
        self.assertIn("Max 10us", exec_text)
        self.assertIn("Max 20us", block_text)

    def test_histogram_variability_overlay_model(self) -> None:
        summary = _hist_summarize([10, 20, 30])
        self.assertAlmostEqual(summary["stddev"], (200 / 3) ** 0.5)

        model = _hist_build_model(
            [10, 20, 30], "ns", "linear", show_variability=True
        )
        self.assertIsNotNone(model)
        self.assertIsNotNone(model["sigma_band"])
        # Min/Max are already evident from the axis extents — no marker lines.
        self.assertEqual(
            [line[1] for line in model["ref_lines"]],
            ["avg", "p5", "p50", "p95"],
        )

        plain = _hist_build_model([10, 20, 30], "ns", "linear")
        self.assertIsNone(plain["sigma_band"])
        self.assertEqual(
            [line[1] for line in plain["ref_lines"]],
            ["avg", "p5", "p50", "p95"],
        )

    def test_histogram_bar_hover_tip(self) -> None:
        model = _hist_build_model([10, 20, 30], "ns", "linear")
        self.assertEqual(model["n"], 3)
        self.assertGreater(len(model["bars"]), 0)
        bx, by, bw, bh, kind, count, edge_lo, edge_hi = model["bars"][0]
        self.assertEqual(kind, "regular")
        self.assertIsInstance(count, int)
        line1, line2 = _hist_bar_tip_lines(
            kind, count, edge_lo, edge_hi, model["n"], "ns", value_as_time=True,
        )
        self.assertIn("–", line1)
        self.assertTrue(line2.endswith("%)"))
        self.assertIn(" of 3 ", line2)
        overflow_tip = _hist_bar_tip_lines(
            "overflow", 2, 0, 0, 10, "ns", value_as_time=True,
        )
        self.assertEqual(overflow_tip, ("> p95", "2 of 10 (20%)"))

    def test_variability_widgets_render(self) -> None:
        points = [
            (100, 10, None),
            (200, 20, None),
            (300, 30, None),
        ]
        scatter = _ScatterWidget(
            points, "ns", QColor("#5B9BD5"), True,
            show_variability=True,
        )
        scatter.resize(820, 320)
        scatter_pm = scatter.grab()
        self.assertFalse(scatter_pm.isNull())

        histogram = _HistogramWidget(
            [10, 20, 30], "ns", QColor("#5B9BD5"), True,
            show_variability=True,
        )
        histogram.resize(820, 240)
        histogram_pm = histogram.grab()
        self.assertFalse(histogram_pm.isNull())

        scatter.close()
        histogram.close()

    def test_metrics_plot_dialog_keeps_histogram_pane(self) -> None:
        from btf_viewer_pkg.stats import _MetricsPlotDialog

        dlg = _MetricsPlotDialog(
            "t",
            [(100, 10, None), (200, 20, None), (300, 30, None)],
            "ns",
            QColor("#5B9BD5"),
            lambda *_a: None,
            True,
            False,
            "FULL",
            "full trace",
        )
        dlg.show()
        self._app.processEvents()
        dlg._fit_plot_panes()
        self._app.processEvents()
        self.assertFalse(dlg._splitter.childrenCollapsible())
        self.assertGreaterEqual(dlg._histogram.height(), 140)
        self.assertGreaterEqual(dlg._splitter.sizes()[1], 140)
        dlg.close()

    def test_stats_help_labels_wrap(self) -> None:
        panel = _StatsPanel()
        lbl = panel._lbl("Pick a metric and task, then open the existing histogram/CDF plot. " * 2)
        self.assertTrue(lbl.wordWrap())
        panel.close()


if __name__ == "__main__":
    unittest.main()
