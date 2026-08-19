"""Statistics table/plot clicks that add annotations must stay on Statistics."""
from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path

BTF_ROOT = Path(__file__).resolve().parents[1]
if str(BTF_ROOT) not in sys.path:
    sys.path.insert(0, str(BTF_ROOT))

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from btf_viewer_pkg._bootstrap import install  # noqa: E402

install()

from PySide6.QtWidgets import QApplication  # noqa: E402

from btf_viewer_pkg.config import _PANEL_TAB_MARKS, _PANEL_TAB_STATS  # noqa: E402
from btf_viewer_pkg.mainwindow import MainWindow  # noqa: E402
from btf_viewer_pkg.parser import _parse_btf  # noqa: E402
from btf_viewer_pkg.stats import _RcSettings  # noqa: E402

from tests import destroy_main_window  # noqa: E402

EXAMPLE_BTF = Path(__file__).resolve().parents[2] / "tracedata" / "example-2cores.btf.gz"


class StatsAnnotationKeepsPanelTest(unittest.TestCase):
    _app: QApplication | None = None

    @classmethod
    def setUpClass(cls) -> None:
        cls._app = QApplication.instance() or QApplication([])

    def setUp(self) -> None:
        self._tmpdir = tempfile.mkdtemp(prefix="btf_stats_ann_")
        self._orig_rc = _RcSettings.RC_PATH
        _RcSettings.RC_PATH = os.path.join(self._tmpdir, "btf_viewer.rc")
        with open(_RcSettings.RC_PATH, "w", encoding="utf-8") as fh:
            fh.write(
                "[view]\nshow_stats=true\nshow_marks=true\n"
                "[window]\ndock_layout_version=12\n"
                "maximized=false\nwidth=1200\nheight=800\n"
            )

    def tearDown(self) -> None:
        _RcSettings.RC_PATH = self._orig_rc

    def test_stats_table_click_adds_annotation_without_leaving_statistics(self) -> None:
        if not EXAMPLE_BTF.is_file():
            self.skipTest(f"missing {EXAMPLE_BTF}")
        trace = _parse_btf(str(EXAMPLE_BTF))
        win = MainWindow()
        self.addCleanup(destroy_main_window, win)
        path = os.path.join(self._tmpdir, "stats-ann.btf")
        tab = win._add_trace_tab(path, trace)
        tab.view.load_trace(trace)
        self._app.processEvents()
        win._focus_panel_tab(_PANEL_TAB_STATS)
        self._app.processEvents()
        self.assertEqual(win._panel_tabs.currentIndex(), _PANEL_TAB_STATS)

        orig_rebuild = win._rebuild_annotation_list

        def steal_to_marks() -> None:
            orig_rebuild()
            win._panel_tabs.setCurrentIndex(_PANEL_TAB_MARKS)

        win._rebuild_annotation_list = steal_to_marks  # type: ignore[method-assign]
        ns = int(trace.time_min + (trace.time_max - trace.time_min) // 4)
        note = "WCET slice test"
        before = len(win._annotations)
        win._on_stats_plot_point_clicked(None, ns, note)
        self._app.processEvents()

        self.assertEqual(win._panel_tabs.currentIndex(), _PANEL_TAB_STATS)
        self.assertEqual(len(win._annotations), before + 1)
        self.assertTrue(any(
            a.note == note and int(a.ns) == ns for a in win._annotations))
