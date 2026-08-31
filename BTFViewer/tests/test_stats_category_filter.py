"""Statistics investigation-category filter pills (web: .stats-cat-filter).

One toggle pill per category (Overview / Triage / Timing / Scheduling / Sync /
Detail); turning a pill off hides every Statistics section in that category.
Mirrors StatisticsPanel.vue ``statsHiddenCategories`` + StatsSectionBlock.vue
``v-show="!categoryHidden"``.
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

from btf_viewer_pkg.config import (  # noqa: E402
    STATS_CATEGORY_LABELS,
    STATS_SECTION_CATEGORIES,
    STATS_SECTION_CATEGORY,
)
from btf_viewer_pkg.mainwindow import MainWindow  # noqa: E402
from btf_viewer_pkg.parser import _parse_btf  # noqa: E402

EXAMPLE_2CORE = BTF_ROOT.parent / "tracedata" / "example-2cores.btf.gz"


def _destroy(win) -> None:
    try:
        win.close()
        win.deleteLater()
    except Exception:
        pass


class StatsCategoryFilterTest(unittest.TestCase):
    _app = None

    @classmethod
    def setUpClass(cls) -> None:
        cls._app = QApplication.instance() or QApplication([])

    def setUp(self) -> None:
        if not EXAMPLE_2CORE.is_file():
            self.skipTest(f"missing {EXAMPLE_2CORE}")

    def _panel(self):
        trace = _parse_btf(str(EXAMPLE_2CORE))
        win = MainWindow()
        self.addCleanup(_destroy, win)
        tab = win._add_trace_tab(str(EXAMPLE_2CORE), trace)
        tab.view.load_trace(trace)
        win._tab_widget.setCurrentIndex(0)
        sp = win._stats_panel
        sp.rebuild(trace)
        for _ in range(8):
            self._app.processEvents()
        return sp

    def test_pills_cover_every_category_with_counts(self) -> None:
        sp = self._panel()
        self.assertEqual(list(sp._cat_pills), list(STATS_SECTION_CATEGORIES))
        want = {c: 0 for c in STATS_SECTION_CATEGORIES}
        for sid in sp._section_header_rows:
            cat = STATS_SECTION_CATEGORY.get(sid)
            if cat in want:
                want[cat] += 1
        for cat, pill in sp._cat_pills.items():
            self.assertIn(STATS_CATEGORY_LABELS[cat], pill.text())
            if want[cat]:
                self.assertIn(str(want[cat]), pill.text())
        self.assertEqual(sp._cat_pill_counts, want)
        self.assertFalse(sp._cat_filter_row.isHidden())
        self.assertTrue(sp._cat_clear_btn.isHidden())
        self.assertFalse(sp._category_filter_active())

    def test_toggling_a_pill_hides_that_category(self) -> None:
        sp = self._panel()
        target = next(
            c for c in STATS_SECTION_CATEGORIES if sp._cat_pill_counts.get(c))
        ids = [sid for sid in sp._section_header_rows
               if STATS_SECTION_CATEGORY.get(sid) == target]
        other = [sid for sid in sp._section_header_rows
                 if STATS_SECTION_CATEGORY.get(sid) != target]

        sp._cat_pills[target].setChecked(False)
        for _ in range(4):
            self._app.processEvents()

        self.assertIn(target, sp._stats_hidden_categories)
        self.assertTrue(sp._category_filter_active())
        self.assertFalse(sp._cat_clear_btn.isHidden())
        for sid in ids:
            self.assertTrue(sp._section_header_rows[sid].isHidden(), sid)
            sep = sp._section_seps.get(sid)
            if sep is not None:
                self.assertTrue(sep.isHidden(), sid)
        for sid in other:
            self.assertFalse(sp._section_header_rows[sid].isHidden(), sid)

    def test_show_all_clears_the_filter(self) -> None:
        sp = self._panel()
        cats = [c for c in STATS_SECTION_CATEGORIES if sp._cat_pill_counts.get(c)]
        for c in cats[:2]:
            sp._cat_pills[c].setChecked(False)
        for _ in range(4):
            self._app.processEvents()
        self.assertTrue(sp._category_filter_active())

        sp._show_all_stats_categories()
        for _ in range(4):
            self._app.processEvents()

        self.assertFalse(sp._category_filter_active())
        self.assertEqual(sp._stats_hidden_categories, set())
        self.assertTrue(sp._cat_clear_btn.isHidden())
        for sid in sp._section_header_rows:
            self.assertFalse(sp._section_header_rows[sid].isHidden(), sid)
        for pill in sp._cat_pills.values():
            self.assertTrue(pill.isChecked())

    def test_filter_survives_a_rebuild(self) -> None:
        sp = self._panel()
        target = next(
            c for c in STATS_SECTION_CATEGORIES if sp._cat_pill_counts.get(c))
        sp._cat_pills[target].setChecked(False)
        for _ in range(4):
            self._app.processEvents()

        sp.rebuild(sp._trace)
        for _ in range(8):
            self._app.processEvents()

        self.assertIn(target, sp._stats_hidden_categories)
        self.assertFalse(sp._cat_pills[target].isChecked())
        ids = [sid for sid in sp._section_header_rows
               if STATS_SECTION_CATEGORY.get(sid) == target]
        self.assertTrue(ids)
        for sid in ids:
            self.assertTrue(sp._section_header_rows[sid].isHidden(), sid)

    def test_web_and_desktop_share_the_category_filter_contract(self) -> None:
        vue = (BTF_ROOT / "web" / "src" / "components"
               / "StatisticsPanel.vue").read_text(encoding="utf-8")
        block = (BTF_ROOT / "web" / "src" / "components"
                 / "StatsSectionBlock.vue").read_text(encoding="utf-8")
        stats = (BTF_ROOT / "btf_viewer_pkg" / "stats.py").read_text(
            encoding="utf-8")
        cfg = (BTF_ROOT / "btf_viewer_pkg" / "config.py").read_text(
            encoding="utf-8")
        # web
        self.assertIn("statsHiddenCategories", vue)
        self.assertIn("toggleStatsCategory", vue)
        self.assertIn("showAllStatsCategories", vue)
        self.assertIn('class="stats-cat-pill"', vue)
        self.assertIn('v-show="!categoryHidden"', block)
        # desktop
        self.assertIn("_stats_hidden_categories", stats)
        self.assertIn("def _apply_category_filter", stats)
        self.assertIn("def _show_all_stats_categories", stats)
        self.assertIn("def _sync_category_pills", stats)
        self.assertIn('"stats_cat_pill"', stats)
        self.assertIn("STATS_CATEGORY_LABELS", cfg)
        for label in ("Overview", "Triage", "Timing", "Scheduling", "Sync",
                      "Detail"):
            self.assertIn(label, cfg)


if __name__ == "__main__":
    unittest.main()
