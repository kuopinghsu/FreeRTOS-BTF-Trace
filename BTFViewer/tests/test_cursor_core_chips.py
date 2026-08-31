"""Cursors panel core-filter chips (web: <CoreFilterChips> above CursorPanel).

The chip row shares the Legend's Core Filter: toggling a chip narrows the
timeline task rows, the legend list, the "Task at cursor" list and the
status-bar chip alike.
"""
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

from PySide6.QtWidgets import QApplication  # noqa: E402

from btf_viewer_pkg.mainwindow import MainWindow, _CoreFilterChips  # noqa: E402
from btf_viewer_pkg.parser import _parse_btf  # noqa: E402

EXAMPLE_2CORE = BTF_ROOT.parent / "tracedata" / "example-2cores.btf.gz"


def _destroy(win) -> None:
    try:
        win.close()
        win.deleteLater()
    except Exception:
        pass


class CoreFilterChipsUnitTest(unittest.TestCase):
    _app = None

    @classmethod
    def setUpClass(cls) -> None:
        cls._app = QApplication.instance() or QApplication([])

    def test_short_labels_and_emit(self) -> None:
        seen = []
        w = _CoreFilterChips(label="Cores")
        w.core_filter_changed.connect(lambda k: seen.append(list(k)))
        w.set_cores(["Core_0", "Core_1", "Core_2"], None)
        self.assertEqual([b.text() for b in w._chips.values()], ["0", "1", "2"])

        # Web model: per-core chips then a trailing "All" clear-link, shown only
        # while a per-core filter is active.
        order = [w._flow.itemAt(i).widget().text() for i in range(w._flow.count())]
        self.assertEqual(order, ["Cores", "0", "1", "2", "All"])
        self.assertTrue(w._all_btn.isHidden())

        w._chips["Core_1"].setChecked(False)
        self.assertEqual(seen, [["Core_0", "Core_2"]])
        self.assertFalse(w._all_btn.isHidden())    # a per-core filter is active

        w._all_btn.click()                         # "All" resets the filter
        self.assertEqual(seen, [["Core_0", "Core_2"], []])
        self.assertTrue(w._all_btn.isHidden())
        self.assertTrue(all(b.isChecked() for b in w._chips.values()))

        w.set_core_filter(["Core_0"])              # external sync — must not re-emit
        self.assertEqual(len(seen), 2)
        self.assertFalse(w._all_btn.isHidden())
        self.assertFalse(w._chips["Core_1"].isChecked())

    def test_hidden_for_single_core(self) -> None:
        w = _CoreFilterChips()
        w.set_cores(["Core_0"], None)
        self.assertFalse(w.isVisibleTo(None))


class CursorChipsIntegrationTest(unittest.TestCase):
    _app = None

    @classmethod
    def setUpClass(cls) -> None:
        cls._app = QApplication.instance() or QApplication([])

    def setUp(self) -> None:
        if not EXAMPLE_2CORE.is_file():
            self.skipTest(f"missing {EXAMPLE_2CORE}")

    def test_chips_scope_the_shared_core_filter(self) -> None:
        trace = _parse_btf(str(EXAMPLE_2CORE))
        win = MainWindow()
        self.addCleanup(_destroy, win)
        tab = win._add_trace_tab(str(EXAMPLE_2CORE), trace)
        tab.view.load_trace(trace)
        win._tab_widget.setCurrentIndex(0)
        self._app.processEvents()
        sc = tab.view._scene

        lo, hi = trace.time_min, trace.time_max
        for f in (0.35, 0.62):
            sc.add_cursor(lo + int((hi - lo) * f))
        win._rebuild_cursor_table()
        self._app.processEvents()

        chips = win._cursor_core_chips
        self.assertFalse(chips.isHidden())
        self.assertEqual([b.text() for b in chips._chips.values()], ["0", "1"])

        all_rows = [t for t in trace.tasks if sc._task_merge_key_matches_filter(t)]

        chips._chips["Core_1"].setChecked(False)   # hide Core_1
        self._app.processEvents()

        self.assertEqual(sorted(sc._core_filter_keys), ["Core_0"])
        self.assertEqual(sorted(win._legend._core_filter_keys), ["Core_0"])
        narrowed = [t for t in trace.tasks if sc._task_merge_key_matches_filter(t)]
        self.assertLess(len(narrowed), len(all_rows))
        self.assertTrue(set(narrowed) <= set(all_rows))
        self.assertFalse(win._status_core_filter_btn.isHidden())

        # Legend now shows the Core Filter as chips (not checkboxes), for any
        # multi-core trace regardless of view mode, and its list follows.
        win._clear_core_filter()
        win._legend.rebuild(trace)
        self._app.processEvents()
        self.assertFalse(win._legend._cores_section.isHidden())
        self.assertEqual(
            [b.text() for b in win._legend._core_chips._chips.values()],
            ["0", "1"])
        win._legend._core_chips._chips["Core_0"].setChecked(False)
        self._app.processEvents()
        self.assertEqual(sorted(win._legend._core_filter_keys), ["Core_1"])
        self.assertEqual(sorted(sc._core_filter_keys), ["Core_1"])
        hidden = sum(
            1 for it in win._legend._task_items.values() if it.isHidden())
        self.assertGreater(hidden, 0)

        # clearing from the legend syncs the cursor chips back
        win._clear_core_filter()
        self._app.processEvents()
        self.assertIsNone(sc._core_filter_keys)
        self.assertTrue(all(b.isChecked() for b in chips._chips.values()))
        self.assertTrue(
            all(b.isChecked() for b in win._legend._core_chips._chips.values()))

    def test_core_filter_alone_marks_statistics_filtered(self) -> None:
        """The Core Filter alone (no cursor scope) must flip the Statistics
        'Filtered' state — top label + every section meta chip — and clearing
        it must clear that state (web: activeFilterSummaryLabel includes the
        'Core: N of M' chip)."""
        from PySide6.QtWidgets import QLabel

        trace = _parse_btf(str(EXAMPLE_2CORE))
        win = MainWindow()
        self.addCleanup(_destroy, win)
        tab = win._add_trace_tab(str(EXAMPLE_2CORE), trace)
        tab.view.load_trace(trace)
        win._tab_widget.setCurrentIndex(0)
        win._stats_panel.rebuild(trace)
        win._legend.rebuild(trace)
        for _ in range(6):
            self._app.processEvents()
        sp = win._stats_panel

        def chip_rows() -> int:
            return sum(
                1 for r in sp._section_header_rows.values()
                if r.findChild(QLabel, "stats_meta_chip_filter") is not None)

        self.assertGreater(len(sp._section_header_rows), 0)
        self.assertFalse(sp._filter_label.isVisible())
        self.assertEqual(chip_rows(), 0)

        # No "Limit to C1–Cn"; just hide a core in the legend.
        win._legend._core_chips._chips["Core_1"].setChecked(False)
        for _ in range(4):
            self._app.processEvents()
        self.assertIn("Core: 1 of 2", sp._filter_label.text())
        self.assertEqual(chip_rows(), len(sp._section_header_rows))

        # Meta order must stay Scope -> Filtered -> category (web
        # StatsSectionHeader.vue), even for a chip inserted live.
        def _seq(row) -> list:
            lay = row.layout()
            out = []
            for i in range(lay.count()):
                it = lay.itemAt(i)
                w = it.widget() if it is not None else None
                if w is not None and w.objectName() in (
                        "stats_meta_chip_scope", "stats_meta_chip_filter",
                        "stats_section_category"):
                    out.append(w.objectName())
            return out

        checked = 0
        for row in sp._section_header_rows.values():
            s = _seq(row)
            if "stats_section_category" in s and "stats_meta_chip_filter" in s:
                self.assertLess(
                    s.index("stats_meta_chip_filter"),
                    s.index("stats_section_category"), s)
                checked += 1
            if "stats_meta_chip_scope" in s and "stats_meta_chip_filter" in s:
                self.assertLess(
                    s.index("stats_meta_chip_scope"),
                    s.index("stats_meta_chip_filter"), s)
        self.assertGreater(checked, 0)

        win._clear_core_filter()
        for _ in range(4):
            self._app.processEvents()
        self.assertEqual(sp._filter_label.text(), "")
        self.assertEqual(chip_rows(), 0)


if __name__ == "__main__":
    unittest.main()
