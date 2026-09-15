from __future__ import annotations

import math
import os
import sys
import unittest
import runpy
import tempfile
from unittest.mock import MagicMock, patch
from pathlib import Path
from types import SimpleNamespace

BTF_ROOT = Path(__file__).resolve().parents[1]
if str(BTF_ROOT) not in sys.path:
    sys.path.insert(0, str(BTF_ROOT))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from btf_viewer_pkg._bootstrap import install  # noqa: E402
install()
from PySide6.QtCore import QEventLoop, QTimer  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402
from btf_viewer_pkg import parser as P  # noqa: E402
from btf_viewer_pkg.stats import _StatsPanel  # noqa: E402

EXAMPLE_8CORES = BTF_ROOT.parent / "tracedata" / "example-8cores.btf.gz"


def _pump(ms: int) -> None:
    loop = QEventLoop()
    QTimer.singleShot(ms, loop.quit)
    loop.exec()


class TestTagRepresentation(unittest.TestCase):
    def test_formats_preserve_values_and_legacy_log_migrates(self) -> None:
        self.assertEqual(P._interpret_tag_value("-1", "uint32"), 0xFFFFFFFF)
        self.assertEqual(P._interpret_tag_value("4294967295", "int32"), -1)
        self.assertEqual(P._interpret_tag_value("1065353216", "float32"), 1.0)
        self.assertEqual(P._interpret_tag_value("255", "log2-uint32"), 255.0)
        self.assertEqual(P._tag_transform(255, P._tag_preferences("log2-uint32")), 8.0)

    def test_wide_sparse_range_recommends_log2(self) -> None:
        samples = [
            P.TagSample("tag3_event", i, float(value), "Core_0", str(value), value)
            for i, value in enumerate((1, 1024, 1048576))
        ]
        trace = SimpleNamespace(
            tag_channels=["tag3_event"],
            tag_samples_by_channel={"tag3_event": samples},
            tag_representations={},
        )
        self.assertEqual(P._recommend_tag_representation(trace, "tag3_event"), "log2-uint32")
        values = [point[1] for point in P._tag_plot_points(trace, "tag3_event")]
        self.assertEqual(values, [1.0, 1024.0, 1048576.0])

    def test_chart_preferences_do_not_change_statistics(self):
        tr = SimpleNamespace(tag_channels=["tag0_event", "tag1_event"], tag_representations={})
        P._update_tag_preferences(tr, "tag0_event", "float32")
        P._update_tag_preferences(tr, "tag0_event", "log2")
        P._update_tag_preferences(tr, "tag0_event", "zero")
        self.assertEqual(P._tag_representation(tr, "tag0_event"), "float32")
        P._update_tag_preferences(tr, "tag0_event", "all")
        self.assertEqual(tr.tag_representations["tag0_event"], tr.tag_representations["tag1_event"])
        P._update_tag_preferences(tr, "tag0_event", "reset")
        self.assertNotIn("tag0_event", tr.tag_representations)
        self.assertTrue(tr.tag_representations["tag1_event"]["includeZero"])

    def test_range_fitting_signed_tiny_and_constant(self):
        for values in ([2, 8], [-20, -2], [1.14e-41, 1.13e-40]):
            self.assertEqual(P._tag_axis_bounds(values), (min(values), max(values)))
            prefs = {"scale": "log2"}
            lo, hi = [P._tag_transform(v, prefs) for v in values]
            self.assertGreater(hi, lo)
            self.assertAlmostEqual(P._tag_inverse(lo, prefs) / values[0], 1)
        self.assertEqual(P._tag_axis_bounds([10, 10]), (9.5, 10.5))
        self.assertEqual(P._tag_axis_bounds([2, 8], {"includeZero": True}), (0, 8))

    def test_rc_round_trip_and_legacy_migration(self):
        from btf_viewer_pkg.stats import _RcSettings
        from btf_viewer_pkg.mainwindow import MainWindow
        with tempfile.TemporaryDirectory() as directory, patch.object(_RcSettings, "RC_PATH", str(Path(directory) / "btf_viewer.rc")):
            trace = SimpleNamespace(tag_channels=["tag0_event"], tag_representations={
                "tag0_event": {"format": "float32", "scale": "log2", "includeZero": True, "alias": "memory usage"}})
            tab = SimpleNamespace(path="/trace/a.btf", trace=trace, view=MagicMock())
            window = SimpleNamespace(_active_tab=tab, _settings=_RcSettings(),
                _trace_state_key=lambda path: MainWindow._trace_state_key(None, path))
            MainWindow._persist_tag_settings(window)
            window._settings = _RcSettings()
            trace.tag_representations = {}
            MainWindow._load_tab_view_state(window, tab)
            self.assertEqual(trace.tag_representations["tag0_event"],
                {"format": "float32", "scale": "log2", "includeZero": True, "alias": "memory usage"})
            window._settings.set("tag_representations", window._trace_state_key(tab.path), '{"tag0_event":"log2-uint32"}')
            MainWindow._load_tab_view_state(window, tab)
            self.assertEqual(trace.tag_representations["tag0_event"],
                {"format": "uint32", "scale": "log2", "includeZero": False})
            tab.path = "/trace/b.btf"
            MainWindow._load_tab_view_state(window, tab)
            self.assertEqual(trace.tag_representations, {})

    def test_histogram_keeps_fractional_axis_labels(self):
        from btf_viewer_pkg.stats import _hist_build_model
        model = _hist_build_model([1.14e-41, 1.13e-40], "ns", "linear", value_as_time=False)
        self.assertTrue(all(label != "0" for _, label in model["x_ticks"]))

    def test_aliases_preserve_channel_identity_and_individual_names(self):
        trace = SimpleNamespace(time_scale="ns", tag_channels=["tag0_event", "tag1_event"],
            tag_representations={}, tag_samples_by_channel={"tag0_event": [
                P.TagSample("tag0_event", 0, 42.0, "Core_0", "42", 42)]})
        P._update_tag_preferences(trace, "tag0_event", "alias:  memory usage  ")
        P._update_tag_preferences(trace, "tag1_event", "alias:CPU usage")
        P._update_tag_preferences(trace, "tag0_event", "float32")
        P._update_tag_preferences(trace, "tag0_event", "all")
        self.assertEqual(P._tag_channel_label("tag1_event", trace), "CPU usage")
        self.assertEqual(P._tag_representation(trace, "tag1_event"), "float32")
        P._update_tag_preferences(trace, "tag0_event", "reset")
        row = P._tag_stats_rows(trace)[0]
        self.assertEqual(row[:2], ("tag0_event", "memory usage"))
        self.assertEqual(row[3], "42")
        self.assertEqual(P._tag_sample_detail_rows(trace)[0]["label"], "memory usage")
        P._update_tag_preferences(trace, "tag0_event", "alias:")
        self.assertEqual(P._tag_channel_label("tag0_event", trace), "Tag 0")

    def test_same_alias_does_not_merge_export_channels(self):
        from btf_viewer_pkg.stats_html import html_tag_overview
        samples = [{"channel": ch, "label": "memory <usage>", "value": str(i),
                    "value_num": i, "time_ns": i, "time": str(i)}
                   for i, ch in enumerate(("tag0_event", "tag1_event"))]
        html = html_tag_overview(samples, time_fmt=lambda s: s["time"])
        self.assertEqual(html.count('aria-label="Tag time series, value versus time"'), 2)
        self.assertIn("memory &lt;usage&gt;", html)
        self.assertNotIn("memory <usage>", html)

    def test_manual_float32_override_drives_stats(self) -> None:
        words = (1065353216, 1073741824)
        samples = [
            P.TagSample("tag0_event", i, float(word), "Core_0", str(word), word)
            for i, word in enumerate(words)
        ]
        trace = SimpleNamespace(
            tag_channels=["tag0_event"],
            tag_samples_by_channel={"tag0_event": samples},
            tag_representations={"tag0_event": "float32"},
        )
        row = P._tag_stats_rows(trace)[0]
        self.assertEqual(row[3], "1")
        self.assertEqual(row[5], "2")

    def test_export_samples_use_selected_representation(self) -> None:
        trace = SimpleNamespace(
            time_scale="ns", tag_channels=["tag0_event"],
            tag_samples_by_channel={"tag0_event": [
                P.TagSample("tag0_event", 0, 1065353216.0, "Core_0", "1065353216", 1065353216)
            ]}, tag_representations={"tag0_event": "float32"},
        )
        self.assertEqual(P._tag_sample_detail_rows(trace)[0]["value_num"], 1.0)

    def test_bundled_float32_path_has_shared_struct_import(self) -> None:
        bundle = BTF_ROOT / "builds" / "btf_viewer.py"
        namespace = runpy.run_path(str(bundle), run_name="btf_viewer_bundle_test")
        self.assertEqual(namespace["_interpret_tag_value"]("1065353216", "float32"), 1.0)


class TestTagRepresentationScrollPreservation(unittest.TestCase):
    """Regression: changing representation must not scroll Tag Analysis away.

    Repro: collapse all sections, expand Task Health and Tag Analysis, jump
    to Tag Analysis (as Find / Symptom Guide / an evidence link would), then
    change representation once that jump's settle window has passed. A stale
    ``_scroll_to_section_requested`` flag — set by the jump but never
    consumed, since nothing rebuilt right after it — used to make this later,
    unrelated rebuild skip its own scroll restore entirely. Separately, the
    restore used to fire before the rebuilt panel's layout had fully settled,
    reading a temporarily-short scrollbar range and freezing there. Both are
    fixed in ``stats.py``'s ``scroll_to_section`` / ``_restore_scroll_y``.
    """

    _app: QApplication | None = None

    @classmethod
    def setUpClass(cls) -> None:
        cls._app = QApplication.instance() or QApplication([])

    @unittest.skipUnless(
        EXAMPLE_8CORES.is_file(), "tracedata/example-8cores.btf.gz not found")
    def test_representation_change_keeps_tag_section_visible(self) -> None:
        app = QApplication.instance()
        trace = P._parse_btf(str(EXAMPLE_8CORES))
        panel = _StatsPanel()
        self.addCleanup(panel.deleteLater)
        panel.rebuild(trace)
        panel.resize(500, 700)
        panel.show()
        app.processEvents()

        panel._collapse_all_sections()
        app.processEvents()
        panel._set_section_collapsed("task_health", False)
        panel._set_section_collapsed("tags", False)
        app.processEvents()

        # "click tag": jump to Tag Analysis, as Find / Symptom Guide / an
        # evidence link would.
        panel.scroll_to_section("tags")
        app.processEvents()

        # Let the jump's settle window (and its scroll-restore-skip flag)
        # fully expire, as it would while the user reads the plot dialog and
        # picks a representation from the dropdown.
        _pump(700)
        app.processEvents()

        def _tags_header_visible() -> bool:
            # Re-fetched each time: rebuild() tears down and reconstructs the
            # section widgets, so a reference captured before it is stale.
            header = panel._section_header_rows["tags"]
            viewport = panel._scroll.viewport()
            top_left = header.mapTo(viewport, header.rect().topLeft())
            return 0 <= top_left.y() <= viewport.height()

        self.assertTrue(_tags_header_visible(), "setup: Tag Analysis should start visible")

        # Exact call the plot dialog's representation dropdown makes.
        panel._set_tag_representation(trace, "tag0_event", "int32")
        for ms in (0, 60, 160, 300, 500):
            _pump(ms)
            app.processEvents()

        self.assertTrue(
            _tags_header_visible(),
            "Tag Analysis header scrolled out of view after changing representation",
        )


if __name__ == "__main__":
    unittest.main()
