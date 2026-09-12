"""Desktop Trace Health status-bar pill + detail popup — web style parity.

Regression coverage for making the desktop status-bar "Caution" indicator
match web's TraceHealthBadge.vue: a rounded pill with a status-colored dot
(not a plain-text QToolButton with a unicode glyph), and a detail popup with
the exact same wording/structure as the web popup (status word · issue
count, the verbatim explanatory note, and per-check Range/Limited lines) —
instead of the previous plain QMessageBox dump.
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

from PySide6.QtWidgets import QApplication, QLabel, QSizePolicy  # noqa: E402

from btf_viewer_pkg.mainwindow import (  # noqa: E402
    MainWindow, _TraceHealthDetailDialog,
)
from btf_viewer_pkg.trace_health import (  # noqa: E402
    build_trace_health_result, trace_health_status_label,
)
from btf_viewer_pkg.parser import _parse_btf  # noqa: E402

from tests import destroy_main_window  # noqa: E402

EXAMPLE_8CORES = BTF_ROOT.parent / "tracedata" / "example-8cores.btf.gz"


class TraceHealthPillStyleTests(unittest.TestCase):
    _app: QApplication | None = None

    @classmethod
    def setUpClass(cls) -> None:
        cls._app = QApplication.instance() or QApplication([])
        cls._app.setQuitOnLastWindowClosed(False)

    def _make_win(self) -> MainWindow:
        win = MainWindow()
        self.addCleanup(destroy_main_window, win)
        win.show()
        return win

    def _load_example_8cores(self, win: MainWindow) -> None:
        if not EXAMPLE_8CORES.is_file():
            self.skipTest(f"missing trace fixture: {EXAMPLE_8CORES}")
        # These tests exercise the pill, not asynchronous file loading. Parse
        # synchronously so Python's cyclic GC cannot run in _ParseThread while
        # the GUI thread is creating/polishing PySide widgets. With Python 3.14
        # and PySide 6.11 that cross-thread Shiboken traversal can intermittently
        # segfault a long-running suite before the assertion is reached.
        path = str(EXAMPLE_8CORES.resolve())
        win._add_trace_tab(path, _parse_btf(path))
        win._refresh_trace_health()

    def test_pill_is_a_styled_widget_not_a_plain_toolbutton_text_dump(self) -> None:
        """The pill must carry an objectName the app QSS can target, a
        dynamic healthStatus property (for status-colored border/dot rules),
        and an icon (the colored dot) — not just a unicode-glyph string."""
        win = self._make_win()
        self._load_example_8cores(win)

        btn = win._status_health_btn
        self.assertTrue(btn.isVisible())
        self.assertEqual(btn.objectName(), "statusHealthBtn")
        # example-8cores.btf.gz has known mutex-pairing issues -> "caution".
        self.assertEqual(win._trace_health_result.get("status"), "caution")
        self.assertEqual(btn.property("healthStatus"), "caution")
        self.assertEqual(btn.text(), f"{trace_health_status_label('caution')} · 1")
        self.assertFalse(btn.icon().isNull(), "pill must show a colored status dot icon")
        # No unicode status glyph left in the text (●/⚠/✕ from the old plain-text button).
        for glyph in ("●", "⚠", "✕"):
            self.assertNotIn(glyph, btn.text())

    def test_pill_qss_rule_exists_for_every_status(self) -> None:
        win = self._make_win()
        qss = QApplication.instance().styleSheet()
        for status in ("pass", "caution", "insufficient"):
            self.assertIn(
                f'QToolButton#statusHealthBtn[healthStatus="{status}"]', qss,
                f"no pill QSS rule for status={status!r}",
            )

    def test_detail_dialog_matches_web_wording_and_structure(self) -> None:
        win = self._make_win()
        self._load_example_8cores(win)
        result = win._trace_health_result
        self.assertTrue(result.get("checks"), "expected at least one check for example-8cores")

        dlg = _TraceHealthDetailDialog(result, parent=win, is_dark=win._is_dark,
                                        ui_font_size=8)
        self.addCleanup(dlg.close)
        labels = dlg.findChildren(QLabel)
        texts = [lab.text() for lab in labels]

        self.assertIn(trace_health_status_label("caution"), texts)
        self.assertIn("· 1 structural issue(s)", texts)

        note_text = next((t for t in texts if "Structural checks on the parsed" in t), None)
        self.assertIsNotNone(note_text, "explanatory note missing")
        # Exact wording parity with web's TraceHealthBadge.vue .th-pop-note.
        self.assertIn(
            "Structural checks on the parsed event model, independent of AI and of "
            "<i>Trace Health (TICK)</i>. Passing means the statistics below rest on a "
            "consistent event stream — not that the system is healthy.",
            note_text,
        )

        check = result["checks"][0]
        self.assertTrue(
            any(check["summary"] in t for t in texts),
            "check summary not rendered in the detail dialog",
        )
        limitations = check.get("metric_limitations") or []
        if limitations:
            self.assertTrue(
                any(t.startswith("Limited: ") and all(m in t for m in limitations) for t in texts),
                "Limited: line missing or incomplete",
            )

    def test_detail_dialog_ok_line_when_no_checks(self) -> None:
        win = self._make_win()
        result = {"status": "pass", "issue_count": 0, "checks": []}
        dlg = _TraceHealthDetailDialog(result, parent=win, is_dark=True, ui_font_size=8)
        self.addCleanup(dlg.close)
        texts = [lab.text() for lab in dlg.findChildren(QLabel)]
        self.assertIn("No structural issues detected in the analysed range.", texts)

    def test_status_bar_health_pill_flanked_by_stretch_spacers(self) -> None:
        """Web centers the badge via `.status-bar { justify-content:
        space-between }`; QStatusBar's own addWidget() zone has no such
        behaviour, so the pill must be flanked by expanding spacers to land
        away from the tightly-packed left info block instead of sitting
        immediately after it."""
        win = self._make_win()
        sb = win.statusBar()

        def find_leaf_layout(lay):
            """QStatusBar nests its message-area row a couple of QBoxLayouts
            deep (QHBoxLayout > QVBoxLayout > QHBoxLayout with the actual
            widgets) — walk down to whichever level directly parents the
            health button."""
            widgets = [lay.itemAt(i).widget() for i in range(lay.count())]
            if win._status_health_btn in widgets:
                return widgets
            for i in range(lay.count()):
                sub = lay.itemAt(i).layout()
                if sub is not None:
                    found = find_leaf_layout(sub)
                    if found is not None:
                        return found
            return None

        widgets = find_leaf_layout(sb.layout())
        self.assertIsNotNone(widgets, "could not find statusHealthBtn's parent layout")
        idx = widgets.index(win._status_health_btn)
        self.assertGreater(idx, 0)
        self.assertLess(idx, len(widgets) - 1)
        before, after = widgets[idx - 1], widgets[idx + 1]
        for spacer in (before, after):
            self.assertIsNotNone(spacer)
            self.assertEqual(spacer.sizePolicy().horizontalPolicy(), QSizePolicy.Policy.Expanding)


if __name__ == "__main__":
    unittest.main()
