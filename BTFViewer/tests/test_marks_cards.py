"""Marks tab: three collapsible cards (web App.vue .rp-card / marksSectionOpen).

Cursors / Cursor Range / Marks are each wrapped in a `_CollapsibleCard` with a
chevron header + count badge; the Marks card no longer carries MarksPanel's own
"Marks (N)" sub-header — the count lives in the card badge.
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

from btf_viewer_pkg.mainwindow import MainWindow, _CollapsibleCard  # noqa: E402
from btf_viewer_pkg.parser import _parse_btf  # noqa: E402

EXAMPLE_2CORE = BTF_ROOT.parent / "tracedata" / "example-2cores.btf.gz"


def _destroy(win) -> None:
    try:
        win.close()
        win.deleteLater()
    except Exception:
        pass


class CollapsibleCardUnitTest(unittest.TestCase):
    _app = None

    @classmethod
    def setUpClass(cls) -> None:
        cls._app = QApplication.instance() or QApplication([])

    def test_toggle_hides_body_and_emits(self) -> None:
        card = _CollapsibleCard("Demo")
        seen = []
        card.toggled.connect(seen.append)
        self.assertTrue(card.is_open())
        card.set_open(False)
        self.assertFalse(card.is_open())
        self.assertTrue(card._body.isHidden())
        self.assertEqual(seen, [False])
        card.set_open(True)
        self.assertTrue(card.is_open())
        self.assertEqual(seen, [False, True])

    def test_count_badge_shows_only_when_set(self) -> None:
        card = _CollapsibleCard("Demo")
        self.assertFalse(card._count.isVisibleTo(card))
        card.set_count("3")
        self.assertEqual(card._count.text(), "3")
        card.set_count(None)
        self.assertFalse(card._count.isVisibleTo(card))


class MarksTabCardsIntegrationTest(unittest.TestCase):
    _app = None

    @classmethod
    def setUpClass(cls) -> None:
        cls._app = QApplication.instance() or QApplication([])

    def setUp(self) -> None:
        if not EXAMPLE_2CORE.is_file():
            self.skipTest(f"missing {EXAMPLE_2CORE}")

    def _win(self):
        trace = _parse_btf(str(EXAMPLE_2CORE))
        win = MainWindow()
        self.addCleanup(_destroy, win)
        tab = win._add_trace_tab(str(EXAMPLE_2CORE), trace)
        tab.view.load_trace(trace)
        win._tab_widget.setCurrentIndex(0)
        for _ in range(4):
            self._app.processEvents()
        return win, trace

    def test_three_cards_exist_and_marks_expands(self) -> None:
        win, _ = self._win()
        for key in ("cursors", "range", "marks"):
            card = getattr(win, f"_marks_card_{key}")
            self.assertIsInstance(card, _CollapsibleCard)
            self.assertTrue(card.is_open())
        self.assertTrue(win._marks_card_marks._expanding)
        self.assertFalse(win._marks_card_cursors._expanding)
        # The old inner "MARKS (N)" sub-header is gone.
        self.assertFalse(hasattr(win, "_marks_count_label"))

    def test_counts_track_cursors_range_and_marks(self) -> None:
        win, trace = self._win()
        lo, hi = trace.time_min, trace.time_max
        win._view._scene.add_cursor(lo + (hi - lo) // 3)
        win._view._scene.add_cursor(lo + 2 * (hi - lo) // 3)
        win._view.cursors_changed.emit(win._view._scene.cursor_times())
        for _ in range(4):
            self._app.processEvents()
        self.assertEqual(win._marks_card_cursors._count.text(), "2")
        self.assertEqual(win._marks_card_range._count.text(), "A–B")

        self.assertEqual(win._marks_card_marks._count.text(), "")
        win._add_annotation_with_note(
            lo + (hi - lo) // 2, "note", show_marks_panel=False)
        for _ in range(4):
            self._app.processEvents()
        self.assertEqual(win._marks_card_marks._count.text(), "1")

    def test_collapse_updates_in_memory_state(self) -> None:
        win, _ = self._win()
        self.assertEqual(
            win._marks_card_state, {"cursors": True, "range": True, "marks": True})
        win._marks_card_cursors.set_open(False)
        for _ in range(3):
            self._app.processEvents()
        self.assertFalse(win._marks_card_state["cursors"])
        self.assertTrue(win._marks_card_cursors._body.isHidden())

    def test_web_and_desktop_share_the_card_contract(self) -> None:
        app_vue = (BTF_ROOT / "web" / "src" / "App.vue").read_text(encoding="utf-8")
        mw = (BTF_ROOT / "btf_viewer_pkg" / "mainwindow.py").read_text(
            encoding="utf-8")
        self.assertIn("marksSectionOpen", app_vue)
        self.assertIn("toggleMarksSection", app_vue)
        self.assertIn('class="rp-card"', app_vue)
        self.assertIn("class _CollapsibleCard", mw)
        self.assertIn("_marks_card_state", mw)
        for key in ("_marks_card_cursors", "_marks_card_range", "_marks_card_marks"):
            self.assertIn(key, mw)


if __name__ == "__main__":
    unittest.main()
