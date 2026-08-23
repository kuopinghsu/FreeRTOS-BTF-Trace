"""Core Utilisation defaults: gauges inside scroll, viewport = gauges + 2 cores."""
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

from PySide6.QtCore import QTimer  # noqa: E402
from PySide6.QtWidgets import QApplication, QScrollArea  # noqa: E402

from btf_viewer_pkg.config import (  # noqa: E402
    STATS_CORES_DEFAULT_VISIBLE_ROWS,
    STATS_CORES_UTIL_DEFAULT_H,
    STATS_LB_GAUGE_H,
    _stats_util_viewport_height,
)
from btf_viewer_pkg.parser import (  # noqa: E402
    BtfTrace,
    TaskSegment,
    _task_merge_key,
)
from btf_viewer_pkg.stats import (  # noqa: E402
    _LoadBalanceGaugeWidget,
    _StatsPanel,
)


def _multi_core_trace(n_cores: int = 4) -> BtfTrace:
    cores = [f"Core_{i}" for i in range(n_cores)]
    segs = []
    seg_map = {}
    core_segs = {c: [] for c in cores}
    task_repr = {}
    for i, core in enumerate(cores):
        label = f"T{i}[{i}]"
        mk = _task_merge_key(label)
        task_repr[mk] = label
        # Uneven active time so load-balance metrics (and the gauge) appear.
        seg = TaskSegment(task=label, start=0, end=1000 * (i + 1), core=core)
        segs.append(seg)
        seg_map[mk] = [seg]
        core_segs[core].append(seg)
    return BtfTrace(
        time_scale="ns",
        tasks=list(seg_map.keys()),
        segments=segs,
        sti_events=[],
        sti_channels=[],
        sti_events_by_target={},
        time_min=0,
        time_max=10_000,
        seg_map_by_merge_key=seg_map,
        core_names=cores,
        core_segs=core_segs,
        task_repr=task_repr,
    )


class CoreUtilDefaultViewTests(unittest.TestCase):
    _app: QApplication | None = None

    @classmethod
    def setUpClass(cls) -> None:
        cls._app = QApplication.instance() or QApplication([])

    def test_gauge_inside_scroll_default_shows_gauge_and_two_cores(self) -> None:
        panel = _StatsPanel()
        self.addCleanup(panel.deleteLater)
        panel.apply_section_table_heights(
            {"cores": STATS_CORES_UTIL_DEFAULT_H})
        panel.rebuild(_multi_core_trace(4))
        # Expand after rebuild: presentation defaults overwrite collapse flags
        # set before rebuild (synthetic traces are not SMP-active without util).
        panel._set_section_collapsed("cores", False)
        panel.resize(400, 800)
        panel.show()
        app = QApplication.instance()
        app.processEvents()
        QTimer.singleShot(0, app.quit)
        app.exec()

        self.assertEqual(STATS_CORES_DEFAULT_VISIBLE_ROWS, 2)
        self.assertEqual(
            STATS_CORES_UTIL_DEFAULT_H,
            STATS_LB_GAUGE_H + _stats_util_viewport_height(2))
        self.assertEqual(
            panel.section_table_heights()["cores"], STATS_CORES_UTIL_DEFAULT_H)

        body = panel._section_bodies["cores"]
        lay = body.layout()
        scroll = None
        for i in range(lay.count()):
            w = lay.itemAt(i).widget()
            if isinstance(w, QScrollArea):
                scroll = w
                break
        self.assertIsInstance(scroll, QScrollArea)
        self.assertEqual(scroll.height(), STATS_CORES_UTIL_DEFAULT_H)
        # Gauges are inside the util scroll (default viewport shows them + 2 rows).
        gauges = scroll.widget().findChildren(_LoadBalanceGaugeWidget)
        self.assertEqual(len(gauges), 1)
        # Content taller than the viewport when there are more than 2 cores.
        self.assertGreater(scroll.widget().sizeHint().height(), scroll.height())
        self.assertGreater(scroll.verticalScrollBar().maximum(), 0)


if __name__ == "__main__":
    unittest.main()
