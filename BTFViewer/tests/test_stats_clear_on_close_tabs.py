"""Statistics must not keep the last trace after Close All / last tab close."""
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

from PySide6.QtWidgets import QApplication, QLabel  # noqa: E402

from btf_viewer_pkg.mainwindow import MainWindow  # noqa: E402
from btf_viewer_pkg.parser import _parse_btf  # noqa: E402
from btf_viewer_pkg.stats import _RcSettings  # noqa: E402

EXAMPLE_BTF = Path(__file__).resolve().parents[2] / "tracedata" / "example-2cores.btf.gz"


def _stats_texts(panel) -> list[str]:
    out = []
    for i in range(panel._ilay.count()):
        w = panel._ilay.itemAt(i).widget()
        if isinstance(w, QLabel):
            out.append(w.text())
    return out


class StatsClearOnCloseTabsTest(unittest.TestCase):
    _app: QApplication | None = None

    @classmethod
    def setUpClass(cls) -> None:
        cls._app = QApplication.instance() or QApplication([])

    def setUp(self) -> None:
        self._tmpdir = tempfile.mkdtemp(prefix="btf_stats_close_")
        self._orig_rc = _RcSettings.RC_PATH
        _RcSettings.RC_PATH = os.path.join(self._tmpdir, "btf_viewer.rc")
        with open(_RcSettings.RC_PATH, "w", encoding="utf-8") as fh:
            fh.write(
                "[view]\nshow_stats=true\n"
                "[window]\ndock_layout_version=11\n"
                "maximized=false\nwidth=1200\nheight=800\n"
            )

    def tearDown(self) -> None:
        _RcSettings.RC_PATH = self._orig_rc

    def test_close_all_tabs_clears_statistics_panel(self) -> None:
        if not EXAMPLE_BTF.is_file():
            self.skipTest(f"missing {EXAMPLE_BTF}")
        trace = _parse_btf(str(EXAMPLE_BTF))
        win = MainWindow()
        self.addCleanup(win.close)
        path = os.path.join(self._tmpdir, "restored.btf")
        tab = win._add_trace_tab(path, trace)
        tab.view.load_trace(trace)
        win._stats_panel.rebuild(trace)
        self._app.processEvents()
        self.assertIs(win._stats_panel._trace, trace)
        self.assertTrue(any("Segments:" in t for t in _stats_texts(win._stats_panel)))

        win._on_close_all_tabs_action()
        self._app.processEvents()

        self.assertEqual(win._tabs, [])
        self.assertIsNone(win._stats_panel._trace)
        texts = _stats_texts(win._stats_panel)
        self.assertTrue(any("Open a trace file" in t for t in texts))
        self.assertFalse(any("Segments:" in t for t in texts))
        self.assertFalse(win._stats_panel._btn_export_csv.isEnabled())
        self.assertEqual(win._legend._task_list.count(), 0)
