"""Parity.md P1: `.btfw` view state must share the canonical portable
Session schema (Desktop <-> Web), instead of Desktop keeping a second,
reduced field list.

Covers:
  - _workspace_has_portable_view_state field-based detection (never by
    ``version`` alone -- legacy Desktop workspace state can also be
    version 2).
  - _workspace_view_state() now delegates to the same builder as the
    standalone Session export (no independent field list / no
    viewport_desktop / trace_name in new exports).
  - Full state round-trip through _build_portable_session_payload() /
    _apply_portable_session_payload() (the same path Session import uses).
  - A Web-shaped portable payload restores completely on Desktop.
  - Legacy reduced Desktop workspace state (pre-unification) still opens
    via _start_pending_workspace().
  - Forward compatibility: unknown fields are ignored, not fatal.
"""
from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

BTF_ROOT = Path(__file__).resolve().parents[1]
if str(BTF_ROOT) not in sys.path:
    sys.path.insert(0, str(BTF_ROOT))

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from btf_viewer_pkg._bootstrap import install  # noqa: E402

install()

from PySide6.QtWidgets import QApplication  # noqa: E402

from btf_viewer_pkg.config import (  # noqa: E402
    PORTABLE_VIEW_STATE_KEYS,
    SESSION_PORTABLE_VERSION,
    _workspace_has_portable_view_state,
)
from btf_viewer_pkg.mainwindow import MainWindow  # noqa: E402
from btf_viewer_pkg.parser import (  # noqa: E402
    BtfTrace, TraceAnnotation, TraceBookmark, _parse_btf, _task_merge_key,
)
from btf_viewer_pkg.workspace import open_workspace  # noqa: E402

EXAMPLE_2CORE = BTF_ROOT.parent / "tracedata" / "example-2cores.btf.gz"


def _destroy(win) -> None:
    try:
        win.close()
        win.deleteLater()
    except Exception:
        pass


class PortableViewStateDetectionTests(unittest.TestCase):
    """Field-based detection must not key off ``version`` alone (Parity.md
    #6): legacy Desktop workspace state can also carry version 2."""

    def test_portable_payload_is_detected(self) -> None:
        view = {
            "version": SESSION_PORTABLE_VERSION,
            "traceName": "demo.btf",
            "timelineViewport": {"timeStart": 0, "timeEnd": 100},
            "timelineOptions": {"viewMode": "core"},
        }
        self.assertTrue(_workspace_has_portable_view_state(view))

    def test_legacy_payload_is_not_detected_even_at_same_version(self) -> None:
        legacy = {
            "version": SESSION_PORTABLE_VERSION,  # same version number as portable
            "trace_name": "demo.btf",
            "cursors": [100, 200],
            "marks": [],
            "markNextId": 1,
            "scopeToCursors": True,
            "viewport_desktop": "...",
        }
        self.assertFalse(_workspace_has_portable_view_state(legacy))

    def test_non_dict_is_not_portable(self) -> None:
        self.assertFalse(_workspace_has_portable_view_state(None))
        self.assertFalse(_workspace_has_portable_view_state([1, 2, 3]))


class WorkspaceViewStateGuiTests(unittest.TestCase):
    """Exercises _set_orientation()/_apply_portable_session_payload(), which
    persist to the shared dev-mode btf_viewer.rc regardless of any
    ``persist=`` flag on the individual show_grid/show_sti calls -- snapshot
    and restore it so running this file does not leave the local dev
    settings mutated for the next manual run."""
    _app = None
    _rc_path = None
    _rc_backup = None

    @classmethod
    def setUpClass(cls) -> None:
        cls._app = QApplication.instance() or QApplication([])
        from btf_viewer_pkg.stats import _RcSettings
        cls._rc_path = Path(_RcSettings.RC_PATH)
        cls._rc_backup = cls._rc_path.read_bytes() if cls._rc_path.is_file() else None

    @classmethod
    def tearDownClass(cls) -> None:
        if cls._rc_backup is not None:
            cls._rc_path.write_bytes(cls._rc_backup)
        elif cls._rc_path.is_file():
            cls._rc_path.unlink()

    def setUp(self) -> None:
        if not EXAMPLE_2CORE.is_file():
            self.skipTest(f"missing {EXAMPLE_2CORE}")
        self.trace = _parse_btf(str(EXAMPLE_2CORE))
        self.win = MainWindow()
        self.addCleanup(_destroy, self.win)
        self.tab = self.win._add_trace_tab(str(EXAMPLE_2CORE), self.trace)
        self.tab.view.load_trace(self.trace)
        self.win._tab_widget.setCurrentIndex(0)
        self.win._stats_panel.rebuild(self.trace)
        for _ in range(3):
            self._app.processEvents()

    def _set_rich_state(self) -> dict:
        """Apply a distinctive, non-default value to every portable field
        this task must round-trip; returns the values chosen for later
        comparison."""
        win, sc = self.win, self.tab.view._scene
        task_key = _task_merge_key(self.trace.tasks[0])

        win._set_view_mode("core")
        win._set_orientation(False)                 # vertical
        win._set_show_grid(False, persist=False)
        win._set_show_sti(False, persist=False)
        win._show_cpu_load = True

        lo, hi = self.trace.time_min, self.trace.time_max
        c1 = lo + int((hi - lo) * 0.2)
        c2 = lo + int((hi - lo) * 0.6)
        sc.clear_cursors()
        sc.add_cursor(c1)
        sc.add_cursor(c2)

        win._bookmarks = [TraceBookmark(id=1, ns=c1, label="bm")]
        win._annotations = [TraceAnnotation(id=2, ns=c2, note="an")]
        win._mark_next_id = 3

        sc._task_filter_q = "core_0"
        sc._migrated_only_filter = True
        sc._core_filter_keys = {"Core_0"}

        win._find_input.setText("worker")
        idx = win._find_mode_combo.findData("exact")
        self.assertGreaterEqual(idx, 0)
        win._find_mode_combo.setCurrentIndex(idx)

        sc.set_highlighted_task(task_key, locked=True)

        win._stats_panel._scope_cb.setChecked(False)
        win._stats_panel._on_scope_toggled(False)

        win._stats_panel._section_collapsed["exec"] = True

        return {
            "task_key": task_key, "c1": c1, "c2": c2,
        }

    def test_workspace_view_state_matches_session_payload(self) -> None:
        """Parity.md #20: Session and Workspace must build the exact same
        portable dict -- one canonical builder, no schema drift."""
        self._set_rich_state()
        session = self.win._build_portable_session_payload()
        workspace_view = self.win._workspace_view_state(self.tab)
        for key in PORTABLE_VIEW_STATE_KEYS:
            self.assertIn(key, session, key)
            self.assertIn(key, workspace_view, key)
            self.assertEqual(workspace_view[key], session[key], key)

    def test_new_workspace_view_state_has_no_legacy_fields(self) -> None:
        """Parity.md #3 / #7: new exports use timelineViewport/traceName,
        never viewport_desktop/trace_name."""
        view = self.win._workspace_view_state(self.tab)
        self.assertNotIn("viewport_desktop", view)
        self.assertNotIn("trace_name", view)
        self.assertIn("timelineViewport", view)
        self.assertIn("traceName", view)
        self.assertTrue(_workspace_has_portable_view_state(view))

    def test_full_state_round_trips_through_apply(self) -> None:
        """Parity.md #9-#14: build the portable payload from rich state,
        reset to defaults, then restore it via the same path Session
        import uses -- every field must come back."""
        chosen = self._set_rich_state()
        win, sc = self.win, self.tab.view._scene
        payload = win._workspace_view_state(self.tab)

        # Reset everything the payload should restore.
        win._set_view_mode("task")
        win._set_orientation(True)
        win._set_show_grid(True, persist=False)
        win._set_show_sti(True, persist=False)
        win._show_cpu_load = False
        sc.clear_cursors()
        win._bookmarks = []
        win._annotations = []
        sc._task_filter_q = ""
        sc._migrated_only_filter = False
        sc._core_filter_keys = None
        win._find_input.setText("")
        win._find_mode_combo.setCurrentIndex(0)
        sc.set_highlighted_task(None)
        win._stats_panel._scope_cb.setChecked(True)
        win._stats_panel._on_scope_toggled(True)
        win._stats_panel._section_collapsed["exec"] = False

        win._apply_portable_session_payload(payload)
        for _ in range(3):
            self._app.processEvents()

        self.assertEqual(sc._view_mode, "core")
        self.assertFalse(sc._horizontal)
        self.assertFalse(win._show_grid)
        self.assertFalse(win._show_sti)
        self.assertTrue(win._show_cpu_load)
        self.assertEqual(sorted(sc.cursor_times()), sorted([chosen["c1"], chosen["c2"]]))
        self.assertEqual(len(win._bookmarks), 1)
        self.assertEqual(len(win._annotations), 1)
        self.assertEqual(sc._task_filter_q, "core_0")
        self.assertTrue(sc._migrated_only_filter)
        self.assertEqual(sc._core_filter_keys, {"Core_0"})
        self.assertEqual(win._find_input.text(), "worker")
        self.assertEqual(win._find_mode_combo.currentData(), "exact")
        self.assertEqual(sc._locked_task, chosen["task_key"])
        self.assertFalse(win._stats_panel._scope_cb.isChecked())
        self.assertTrue(win._stats_panel._section_collapsed.get("exec"))

    def test_web_shaped_payload_restores_completely_on_desktop(self) -> None:
        """Parity.md #21: a Web-authored .btfw view_state (built the same
        shape as sessionPortable.js's buildPortableSession) must restore
        fully on Desktop."""
        win, sc = self.win, self.tab.view._scene
        lo, hi = self.trace.time_min, self.trace.time_max
        c1 = lo + int((hi - lo) * 0.3)
        web_view_state = {
            "version": SESSION_PORTABLE_VERSION,
            "traceName": "example-2cores.btf",
            "cursors": [c1, None],
            "marks": [
                {"id": 1, "ns": c1, "label": "web-bm", "type": "bookmark"},
                {"id": 2, "ns": c1, "label": "web-an", "type": "annotation"},
            ],
            "markNextId": 3,
            "timelineOptions": {
                "viewMode": "core", "orientation": "v",
                "showGrid": False, "showSti": False,
                "showCpuLoad": True, "darkMode": win._is_dark,
            },
            "tabFilters": {
                "taskFilterText": "web-task", "migratedOnlyFilter": True,
                "coreFilterKeys": ["Core_1"],
            },
            "findQuery": "spi", "findMode": "regex",
            "pinnedHighlightKey": None,
            "scopeToCursors": False,
            "openPlot": None,
            "statsSectionCollapsed": {"exec": True},
        }
        self.assertTrue(_workspace_has_portable_view_state(web_view_state))

        win._apply_portable_session_payload(web_view_state)
        for _ in range(3):
            self._app.processEvents()

        self.assertEqual(sc._view_mode, "core")
        self.assertFalse(sc._horizontal)
        self.assertFalse(win._show_grid)
        self.assertFalse(win._show_sti)
        self.assertTrue(win._show_cpu_load)
        self.assertEqual(sc.cursor_times(), [c1])
        self.assertEqual(len(win._bookmarks), 1)
        self.assertEqual(len(win._annotations), 1)
        self.assertEqual(win._bookmarks[0].label, "web-bm")
        self.assertEqual(win._annotations[0].note, "web-an")
        self.assertEqual(sc._task_filter_q, "web-task")
        self.assertTrue(sc._migrated_only_filter)
        self.assertEqual(sc._core_filter_keys, {"Core_1"})
        self.assertEqual(win._find_input.text(), "spi")
        self.assertEqual(win._find_mode_combo.currentData(), "regex")
        self.assertFalse(win._stats_panel._scope_cb.isChecked())
        self.assertTrue(win._stats_panel._section_collapsed.get("exec"))

    def test_legacy_desktop_workspace_still_opens(self) -> None:
        """Parity.md #23: an old, reduced-schema Desktop .btfw payload must
        still restore cursors/marks/scope without raising, through the
        same _start_pending_workspace() dispatch used for real files."""
        win, sc = self.win, self.tab.view._scene
        lo, hi = self.trace.time_min, self.trace.time_max
        c1, c2 = lo + int((hi - lo) * 0.1), lo + int((hi - lo) * 0.4)
        legacy_view = {
            "version": SESSION_PORTABLE_VERSION,
            "trace_name": "example-2cores.btf",
            "cursors": [c1, c2],
            "marks": [{"id": 1, "ns": c1, "label": "old-bm", "type": "bookmark"}],
            "markNextId": 2,
            "scopeToCursors": False,
            "viewport_desktop": "",
        }
        self.assertFalse(_workspace_has_portable_view_state(legacy_view))

        win._pending_workspace = {
            "kind": "workspace", "view_state": legacy_view,
            "investigation": None, "ai_case": None,
        }
        try:
            win._start_pending_workspace()
        except Exception as exc:  # pragma: no cover - assertion message only
            self.fail(f"legacy workspace restore raised: {exc!r}")
        for _ in range(3):
            self._app.processEvents()

        self.assertEqual(sorted(sc.cursor_times()), [c1, c2])
        self.assertEqual(len(win._bookmarks), 1)
        self.assertEqual(win._bookmarks[0].label, "old-bm")
        self.assertFalse(win._stats_panel._scope_cb.isChecked())

    def test_run_workspace_export_writes_portable_view_state_to_disk(self) -> None:
        """End-to-end: _run_workspace_export() -> real .btfw on disk ->
        open_workspace() must contain the portable schema, and re-opening it
        through _start_pending_workspace() must restore the rich state
        (Parity.md #17-#18 architecture, exercised through the real file
        format rather than an in-memory dict)."""
        chosen = self._set_rich_state()
        win, sc = self.win, self.tab.view._scene

        with tempfile.TemporaryDirectory() as tmp:
            out_path = str(Path(tmp) / "roundtrip.btfw")
            with patch(
                "btf_viewer_pkg.mainwindow.QFileDialog.getSaveFileName",
                return_value=(out_path, ""),
            ):
                win._run_workspace_export(embed=True)
            self.assertTrue(Path(out_path).is_file())

            ws = open_workspace(out_path)
            view = ws["view_state"]
            self.assertTrue(_workspace_has_portable_view_state(view))
            for key in PORTABLE_VIEW_STATE_KEYS:
                self.assertIn(key, view)
            self.assertNotIn("viewport_desktop", view)
            self.assertNotIn("trace_name", view)

            # Reset, then restore through the real workspace-open dispatch.
            win._set_view_mode("task")
            win._set_orientation(True)
            sc.clear_cursors()
            win._bookmarks, win._annotations = [], []
            win._stats_panel._scope_cb.setChecked(True)
            win._stats_panel._on_scope_toggled(True)

            win._pending_workspace = ws
            win._start_pending_workspace()
            for _ in range(3):
                self._app.processEvents()

            self.assertEqual(sc._view_mode, "core")
            self.assertFalse(sc._horizontal)
            self.assertEqual(
                sorted(sc.cursor_times()), sorted([chosen["c1"], chosen["c2"]]))
            self.assertEqual(len(win._bookmarks), 1)
            self.assertEqual(len(win._annotations), 1)
            self.assertFalse(win._stats_panel._scope_cb.isChecked())

    def test_forward_compatible_unknown_field_is_ignored(self) -> None:
        """Parity.md #24: an unknown future field must not break loading."""
        view = self.win._workspace_view_state(self.tab)
        view["futureOption"] = True
        view["statsSectionCollapsed"] = {"not_a_real_section": True}
        try:
            self.win._apply_portable_session_payload(view)
        except Exception as exc:  # pragma: no cover - assertion message only
            self.fail(f"forward-compatible payload raised: {exc!r}")


if __name__ == "__main__":
    unittest.main()
