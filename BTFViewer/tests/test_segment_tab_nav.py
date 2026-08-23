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
EXAMPLE_2CORE_BTF = Path(__file__).resolve().parents[2] / "tracedata" / "example-2cores.btf.gz"
WEB_APP = Path(__file__).resolve().parents[1] / "web" / "src" / "App.vue"


class SegmentTabNavWebParityTest(unittest.TestCase):
    """Desktop <-> web: cycleHighlightedSegment() must branch the same way
    as _cycle_highlighted_task() - "already selected" (exact segment *or*
    a task merely pinned via the legend) keeps the pre-existing
    next/previous-task cycling; only a *fully unselected* state uses the
    new marker/viewport-start anchored first stop."""

    def test_web_source_has_earliest_marker_helper_and_anchor_fallback(self) -> None:
        app = WEB_APP.read_text(encoding="utf-8")
        self.assertIn("function _earliestMarkerInViewport()", app)
        self.assertIn("function cycleHighlightedSegment(forward)", app)
        # Priority: cursors before marks, viewport start as the last resort.
        self.assertIn("for (const c of cursors.value)", app)
        self.assertIn("for (const m of marks.value)", app)
        self.assertIn("_earliestMarkerInViewport()", app)
        self.assertIn("getViewport?.()?.timeStart", app)

    def test_web_branches_on_curTaskKey_not_just_exact_segment(self) -> None:
        """A task pinned via the legend (no exact segment) must still use
        the old cycling branch, matching Desktop's `cur_task is not None`
        check - not the new anchor-based first stop."""
        app = WEB_APP.read_text(encoding="utf-8")
        self.assertIn("if (curTaskKey != null) {", app)
        # The anchor-based first stop must live in the *other* branch: the
        # first _earliestMarkerInViewport() call inside cycleHighlightedSegment
        # (skipping its definition higher up in the file) comes after the
        # matching "} else {".
        fn_start = app.index("function cycleHighlightedSegment(forward) {")
        idx_branch = app.index("if (curTaskKey != null) {", fn_start)
        else_pos = app.index("} else {", idx_branch)
        idx_anchor = app.index("_earliestMarkerInViewport()", else_pos)
        self.assertGreater(idx_anchor, else_pos)

    def test_web_falls_back_to_viewport_center_core_like_desktop(self) -> None:
        """Desktop's _core_at_viewport_center() must mirror the web app's
        pre-existing getCoreAtViewportCenter() fallback - not an arbitrary
        first/last core - when nothing is locked in Core view."""
        app = WEB_APP.read_text(encoding="utf-8")
        self.assertIn("getCoreAtViewportCenter?.()", app)
        self.assertIn("let curCore = cur?.core ?? null", app)
        desktop_src = (Path(__file__).resolve().parents[1] / "btf_viewer_pkg" /
                       "view.py").read_text(encoding="utf-8")
        self.assertIn("def _core_at_viewport_center(", desktop_src)
        self.assertIn("self._core_at_viewport_center(core_names, core_tasks)",
                       desktop_src)

    def test_web_scopes_legend_pin_to_core_containing_task_before_center_fallback(
            self) -> None:
        """A task pinned via the legend (curCore starts null) must scope to
        a core that actually contains it before falling back to the
        viewport-center core - matching Desktop's cur_task-core search."""
        app = WEB_APP.read_text(encoding="utf-8")
        fn_start = app.index("function cycleHighlightedSegment(forward) {")
        fn_body = app[fn_start:fn_start + 2000]
        idx_search = fn_body.index("tasks.some(t => taskMergeKey(t) === curTaskKey")
        idx_center_fallback = fn_body.index("getCoreAtViewportCenter?.()")
        self.assertLess(idx_search, idx_center_fallback)

    def test_web_filters_navSegs_by_active_task_filters(self) -> None:
        """Tab/Shift+Tab must never surface a segment hidden by the active
        task filter (search text / migrated-only / heatmap selection) -
        matching Desktop's task_ok() check inside _pick_next_task_by_time."""
        app = WEB_APP.read_text(encoding="utf-8")
        self.assertIn(
            "import { taskPassesRowFilter, rawTaskNameMatchesTextFilter, "
            "normalizeTaskFilterText, coreFilterActive } from './utils/taskFilter.js'", app)
        fn_start = app.index("function cycleHighlightedSegment(forward) {")
        fn_body = app[fn_start:fn_start + 2800]
        idx_filter = fn_body.index("navSegs = navSegs.filter(s => taskPassesRowFilter(")
        idx_empty_check = fn_body.index("if (!navSegs || navSegs.length === 0) return")
        self.assertLess(idx_filter, idx_empty_check)


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

    def _make_2core_timeline(self, width: int = 1200, height: int = 700):
        if not EXAMPLE_2CORE_BTF.is_file():
            self.skipTest(f"missing trace fixture: {EXAMPLE_2CORE_BTF}")
        view = TimelineView()
        view.resize(width, height)
        view.show()
        trace = _parse_btf(str(EXAMPLE_2CORE_BTF))
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
        from PySide6.QtCore import QPoint

        view, sc, trace = self._make_timeline()
        # Zoom in near the trace start so the trace end is well outside the
        # (now much narrower) viewport.
        view._do_zoom(50.0, QPoint(200, 300))
        self._app.processEvents()
        lo, hi = view._visible_time_ns_range()
        if trace.time_max <= hi:
            self.skipTest("trace too short to place an out-of-viewport cursor")
        sc.add_cursor(trace.time_max)
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


class CoreViewFallbackScopeTest(_QtTestBase):
    """When nothing is locked in Core view, the core to scope Tab/Shift+Tab
    to must be the core at the viewport's center - matching the web app's
    getCoreAtViewportCenter() fallback - not an arbitrary first/last core."""

    def test_core_at_viewport_center_matches_row_under_center(self) -> None:
        view, sc, trace = self._make_timeline()
        view.set_view_mode("core")
        self._app.processEvents()

        core_names = trace.core_names
        self.assertTrue(core_names)
        center = view._core_at_viewport_center(core_names, trace.core_task_order)
        self.assertIn(center, core_names)

    def test_tab_with_nothing_selected_scopes_to_viewport_center_core(self) -> None:
        view, sc, trace = self._make_timeline()
        view.set_view_mode("core")
        self._app.processEvents()
        self.assertIsNone(sc._locked_task)

        core_names = trace.core_names
        expected_core = view._core_at_viewport_center(core_names, trace.core_task_order)
        self.assertTrue(view._cycle_highlighted_task(True))
        self.assertEqual(sc._locked_core, expected_core)

    def test_shift_tab_with_nothing_selected_scopes_to_same_core_as_tab(self) -> None:
        """Direction must not change which core is picked when nothing is
        selected: both keys anchor to the same viewport-center core."""
        view, sc, trace = self._make_timeline()
        view.set_view_mode("core")
        self._app.processEvents()

        self.assertTrue(view._cycle_highlighted_task(True))
        tab_core = sc._locked_core

        sc.set_highlighted_task(None)
        self.assertIsNone(sc._locked_task)
        self.assertTrue(view._cycle_highlighted_task(False))
        self.assertEqual(sc._locked_core, tab_core)


class CoreViewLegendPinScopeTest(_QtTestBase):
    """A task pinned via the legend (locked, but with no specific core - as
    happens with a plain click on a legend swatch) must scope Tab/Shift+Tab
    to a core that actually contains that task, not just whichever core is
    at the viewport center."""

    def test_legend_pin_scopes_to_core_containing_the_task(self) -> None:
        view, sc, trace = self._make_2core_timeline()
        view.set_view_mode("core")
        self._app.processEvents()

        core_names = trace.core_names
        if len(core_names) < 2:
            self.skipTest("fixture needs >= 2 cores")
        center_core = view._core_at_viewport_center(core_names, trace.core_task_order)
        other_core = next(c for c in core_names if c != center_core)
        center_mks = {_task_merge_key(t) for t in trace.core_task_order.get(center_core, [])}
        only_on_other = [
            t for t in trace.core_task_order.get(other_core, [])
            if _task_merge_key(t) not in center_mks
        ]
        if not only_on_other:
            self.skipTest("no task exclusive to the non-center core in this fixture")

        mk = _task_merge_key(only_on_other[0])
        sc.set_highlighted_task(mk, locked=True)  # legend pin: no core_name
        self.assertIsNone(sc._locked_core)

        self.assertTrue(view._cycle_highlighted_task(True))
        self.assertEqual(sc._locked_core, other_core)


class TabRespectsActiveFiltersTest(_QtTestBase):
    """Tab/Shift+Tab must never land on a segment whose task is hidden by
    the active task filter (search text / migrated-only / heatmap), just
    like the rendered timeline itself."""

    def test_heatmap_filter_restricts_pick_to_allowed_tasks(self) -> None:
        view, sc, trace = self._make_timeline()
        tick_mk = _task_merge_key("TICK")
        all_mks = [mk for mk in trace.tasks if mk != tick_mk]
        self.assertGreaterEqual(len(all_mks), 2, "fixture needs >= 2 non-TICK tasks")
        allowed_mk = all_mks[0]
        sc.set_heatmap_task_filter({allowed_mk}, label="test")

        self.assertTrue(view._cycle_highlighted_task(True))
        self.assertEqual(sc._locked_task, allowed_mk)
        # Nothing else is allowed under this filter, and same-task repeats
        # are skipped once something is selected: no further pick exists.
        self.assertFalse(view._cycle_highlighted_task(True))

    def test_text_filter_first_stop_only_matches_filtered_tasks(self) -> None:
        view, sc, trace = self._make_timeline()
        tick_mk = _task_merge_key("TICK")
        all_mks = {mk for mk in trace.tasks if mk != tick_mk}
        self.assertGreaterEqual(len(all_mks), 2, "fixture needs >= 2 non-TICK tasks")
        target_mk = next(iter(all_mks))
        sc.set_task_filter(target_mk)  # merge keys are unique -> exact match

        self.assertTrue(view._cycle_highlighted_task(True))
        self.assertEqual(sc._locked_task, target_mk)

    def test_migrated_only_filter_restricts_task_view_pick(self) -> None:
        view, sc, trace = self._make_2core_timeline()
        migrated_mks = {
            mk for mk in trace.tasks
            if sum(1 for c in trace.core_names
                   if any(_task_merge_key(t) == mk for t in trace.core_task_order.get(c, [])))
            >= 2
        }
        if not migrated_mks:
            self.skipTest("fixture has no task migrating across cores")
        sc.set_migrated_only_filter(True)

        picked_any = False
        for _ in range(20):
            if not view._cycle_highlighted_task(True):
                break
            picked_any = True
            self.assertIn(sc._locked_task, migrated_mks)
        self.assertTrue(picked_any)


if __name__ == "__main__":
    unittest.main()
