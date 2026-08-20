"""Tab / Shift+Tab task-segment navigation: first-stop anchoring.

Only the *first stop* (nothing selected yet) changed: it now jumps to the
first segment at/after the earliest cursor/bookmark/annotation visible in
the viewport, or the viewport start edge if none are visible. Once a task
is selected, Tab/Shift+Tab keep cycling to the next/previous task exactly
as before (same-task repeats skipped) - covered by the "still cycles"
regression test below.
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

from btf_viewer_pkg.parser import _parse_btf, _task_merge_key  # noqa: E402
from btf_viewer_pkg.view import TimelineView  # noqa: E402

EXAMPLE_BTF = Path(__file__).resolve().parents[2] / "tracedata" / "example.btf.gz"


class _QtTestBase(unittest.TestCase):
    _app: "QApplication | None" = None

    @classmethod
    def setUpClass(cls) -> None:
        cls._app = QApplication.instance() or QApplication([])

    def _make_timeline(self, width: int = 1200, height: int = 700):
        if not EXAMPLE_BTF.is_file():
            self.skipTest(f"missing trace fixture: {EXAMPLE_BTF}")
        view = TimelineView()
        view.resize(width, height)
        view.show()
        trace = _parse_btf(str(EXAMPLE_BTF))
        view.load_trace(trace)
        self._app.processEvents()
        view.zoom_fit()
        self._app.processEvents()
        return view, view._scene, trace


class EarliestMarkerInViewportTest(_QtTestBase):
    def test_none_when_no_markers(self) -> None:
        view, sc, _trace = self._make_timeline()
        self.assertIsNone(view._earliest_marker_in_viewport())

    def test_cursor_inside_viewport_is_found(self) -> None:
        view, sc, _trace = self._make_timeline()
        lo, hi = view._visible_time_ns_range()
        mid = (lo + hi) // 2
        sc.add_cursor(mid)
        self.assertEqual(view._earliest_marker_in_viewport(), mid)

    def test_cursor_outside_viewport_is_ignored(self) -> None:
        view, sc, trace = self._make_timeline()
        lo, _hi = view._visible_time_ns_range()
        # A cursor placed exactly at the trace time_min is still >= lo after
        # zoom_fit (whole trace visible), so force it out of range instead.
        out_of_range = lo - 1_000_000_000
        sc._cursor_times = [max(trace.time_min, out_of_range)]
        if sc._cursor_times[0] >= lo:
            self.skipTest("trace too short to place an out-of-viewport cursor")
        self.assertIsNone(view._earliest_marker_in_viewport())

    def test_mark_data_bookmark_is_found_and_priority_is_earliest(self) -> None:
        view, sc, _trace = self._make_timeline()
        lo, hi = view._visible_time_ns_range()
        early = lo + (hi - lo) // 4
        late = lo + (hi - lo) // 2
        sc.add_cursor(late)
        sc._mark_data = [(early, "note", "#FFD700", "bookmark", 1)]
        self.assertEqual(view._earliest_marker_in_viewport(), early)


class CycleHighlightedTaskFirstStopTest(_QtTestBase):
    def test_tab_with_nothing_selected_picks_first_segment_in_viewport(self) -> None:
        view, sc, trace = self._make_timeline()
        self.assertIsNone(sc._locked_task)
        self.assertTrue(view._cycle_highlighted_task(True))
        self.assertIsNotNone(sc._locked_segment_key)
        vp_lo, _vp_hi = view._visible_time_ns_range()
        self.assertGreaterEqual(sc._locked_ns, vp_lo)
        expected_first = min(
            s.start for s in trace.segments
            if s.task and _task_merge_key(s.task) != _task_merge_key("TICK")
            and s.start >= vp_lo
        )
        self.assertEqual(sc._locked_ns, expected_first)

    def test_shift_tab_with_nothing_selected_matches_tab(self) -> None:
        """No current segment: Tab and Shift+Tab establish the same first stop."""
        view, sc, _trace = self._make_timeline()
        self.assertTrue(view._cycle_highlighted_task(True))
        first_pick = (sc._locked_ns, sc._locked_task)

        sc.set_highlighted_task(None)
        self.assertIsNone(sc._locked_task)
        self.assertTrue(view._cycle_highlighted_task(False))
        self.assertEqual((sc._locked_ns, sc._locked_task), first_pick)

    def test_tab_prioritizes_marker_over_viewport_start(self) -> None:
        view, sc, trace = self._make_timeline()
        vp_lo, vp_hi = view._visible_time_ns_range()
        mid_ns = (vp_lo + vp_hi) // 2
        sc.add_cursor(mid_ns)

        self.assertTrue(view._cycle_highlighted_task(True))
        self.assertGreaterEqual(sc._locked_ns, mid_ns)

        segs_before_mid = [
            s.start for s in trace.segments
            if s.task and _task_merge_key(s.task) != _task_merge_key("TICK")
            and vp_lo <= s.start < mid_ns
        ]
        if segs_before_mid:
            # Confirms the plain viewport-start pick would have landed earlier
            # than the marker-anchored pick actually did.
            self.assertGreater(sc._locked_ns, min(segs_before_mid))

    def test_once_selected_further_tabs_still_cycle_by_task(self) -> None:
        """Follow-up presses keep the pre-existing same-task-skip cycling."""
        view, sc, _trace = self._make_timeline()
        self.assertTrue(view._cycle_highlighted_task(True))
        first_task = sc._locked_task
        self.assertTrue(view._cycle_highlighted_task(True))
        second_task = sc._locked_task
        # Same-task repeats are skipped once something is selected.
        self.assertNotEqual(first_task, second_task)

    def test_shift_tab_after_selection_moves_backward(self) -> None:
        view, sc, _trace = self._make_timeline()
        view._cycle_highlighted_task(True)
        view._cycle_highlighted_task(True)
        mid_ns = sc._locked_ns
        self.assertTrue(view._cycle_highlighted_task(False))
        self.assertLessEqual(sc._locked_ns, mid_ns)


if __name__ == "__main__":
    unittest.main()
