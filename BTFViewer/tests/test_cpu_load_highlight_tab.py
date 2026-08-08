"""Lock-highlighted CPU load must survive switching trace tabs."""
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

from btf_viewer_pkg.mainwindow import MainWindow, _CpuLoadGraph  # noqa: E402
from btf_viewer_pkg.parser import _parse_btf, _task_merge_key  # noqa: E402
from btf_viewer_pkg.stats import _RcSettings  # noqa: E402
from btf_viewer_pkg.view import TimelineView  # noqa: E402

EXAMPLE_BTF = Path(__file__).resolve().parents[2] / "tracedata" / "example-2cores.btf.gz"


def _first_user_mk(trace) -> str:
    for name in trace.tasks:
        mk = _task_merge_key(name)
        upper = mk.upper()
        if upper.startswith("IDLE") or upper.startswith("TICK") or upper.startswith("CORE_"):
            continue
        return mk
    raise AssertionError("no user task in fixture trace")


class CpuLoadHighlightTabTest(unittest.TestCase):
    _app: QApplication | None = None

    @classmethod
    def setUpClass(cls) -> None:
        cls._app = QApplication.instance() or QApplication([])

    def setUp(self) -> None:
        self._tmpdir = tempfile.mkdtemp(prefix="btf_cpu_hl_")
        self._orig_rc = _RcSettings.RC_PATH
        _RcSettings.RC_PATH = os.path.join(self._tmpdir, "btf_viewer.rc")
        with open(_RcSettings.RC_PATH, "w", encoding="utf-8") as fh:
            fh.write(
                "[view]\n"
                "show_stats=true\n"
                "show_cpu_load=true\n"
                "[window]\n"
                "dock_layout_version=11\n"
                "maximized=false\n"
                "width=1200\n"
                "height=800\n"
            )

    def tearDown(self) -> None:
        _RcSettings.RC_PATH = self._orig_rc

    def test_set_trace_same_object_keeps_selected_task(self) -> None:
        if not EXAMPLE_BTF.is_file():
            self.skipTest(f"missing {EXAMPLE_BTF}")
        trace = _parse_btf(str(EXAMPLE_BTF))
        mk = _first_user_mk(trace)
        view = TimelineView()
        self.addCleanup(view.deleteLater)
        graph = _CpuLoadGraph(view)
        self.addCleanup(graph.deleteLater)
        graph.set_trace(trace)
        graph.set_task(mk, True)
        self.assertEqual(graph._selected_task, mk)
        kinds = [row[0] for row in graph._get_rows()]
        self.assertTrue(kinds, "expected CPU load rows")
        self.assertNotIn("total", kinds)
        graph.set_trace(trace)
        self.assertEqual(graph._selected_task, mk)
        self.assertNotIn("total", [row[0] for row in graph._get_rows()])

    def test_tab_switch_keeps_highlighted_task_cpu_load(self) -> None:
        if not EXAMPLE_BTF.is_file():
            self.skipTest(f"missing {EXAMPLE_BTF}")
        trace_a = _parse_btf(str(EXAMPLE_BTF))
        trace_b = _parse_btf(str(EXAMPLE_BTF))
        mk = _first_user_mk(trace_a)

        win = MainWindow()
        self.addCleanup(win.close)
        path_a = os.path.join(self._tmpdir, "a.btf")
        path_b = os.path.join(self._tmpdir, "b.btf")
        tab_a = win._add_trace_tab(path_a, trace_a)
        tab_a.view.load_trace(trace_a)
        tab_a.cpu_load_graph.set_trace(trace_a)
        tab_a.view._scene.set_highlighted_task(mk, locked=True)
        self._app.processEvents()
        self.assertEqual(tab_a.cpu_load_graph._selected_task, mk)

        tab_b = win._add_trace_tab(path_b, trace_b)
        tab_b.view.load_trace(trace_b)
        tab_b.cpu_load_graph.set_trace(trace_b)
        self._app.processEvents()

        win._tab_widget.setCurrentIndex(0)
        self._app.processEvents()

        self.assertIs(win._active_tab, tab_a)
        self.assertEqual(tab_a.view._scene._locked_task, mk)
        self.assertEqual(
            tab_a.cpu_load_graph._selected_task, mk,
            "CPU load should stay filtered to the lock-highlighted task",
        )
        self.assertNotIn("total", [row[0] for row in tab_a.cpu_load_graph._get_rows()])
