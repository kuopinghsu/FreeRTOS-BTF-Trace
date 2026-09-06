"""Desktop Statistics Reference language toggle (EN / zh-TW).

Regression coverage for the dual-language feature: btf_viewer.hlp now holds
a JSON envelope {"en": ..., "zh-tw": ...} (see scripts/build_docs_html.py
and stats_reference.py's _load_pages()/_toggle_lang()), and the chosen
language persists to btf_viewer.rc's [help] stats_ref_lang key via the
MainWindow's shared _RcSettings instance — the same mechanism used for
every other view preference. Web parity: web/tests covers the equivalent
localStorage behaviour in StatsReferenceViewer.vue by inspection/build,
since it has no jsdom-backed component test harness.
"""
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

from btf_viewer_pkg.mainwindow import MainWindow  # noqa: E402
from btf_viewer_pkg.stats import _RcSettings  # noqa: E402
from btf_viewer_pkg.stats_reference import StatsReferenceViewer  # noqa: E402

from tests import destroy_main_window  # noqa: E402


class StatsReferenceLangToggleTests(unittest.TestCase):
    _app: QApplication | None = None

    @classmethod
    def setUpClass(cls) -> None:
        cls._app = QApplication.instance() or QApplication([])
        cls._app.setQuitOnLastWindowClosed(False)

    def setUp(self) -> None:
        self._tmpdir = tempfile.mkdtemp(prefix="btf_stats_lang_")
        self._orig_rc = _RcSettings.RC_PATH
        _RcSettings.RC_PATH = os.path.join(self._tmpdir, "btf_viewer.rc")

    def tearDown(self) -> None:
        _RcSettings.RC_PATH = self._orig_rc

    def _make_win(self) -> MainWindow:
        win = MainWindow()
        self.addCleanup(destroy_main_window, win)
        win.show()
        return win

    def _make_viewer(self, win: MainWindow) -> StatsReferenceViewer:
        viewer = StatsReferenceViewer(win)
        self.addCleanup(viewer.close)
        return viewer

    def test_defaults_to_english(self) -> None:
        win = self._make_win()
        viewer = self._make_viewer(win)
        self.assertEqual(viewer._lang, "en")
        self.assertEqual(viewer._lang_btn.text(), "EN")

    def test_toggle_switches_doc_html_and_button_label(self) -> None:
        win = self._make_win()
        viewer = self._make_viewer(win)
        viewer.open_section("cores")
        self.assertTrue(viewer._pages, "help_file_path()/_load_pages() found no built .hlp")
        en_html = viewer._doc_html

        viewer._toggle_lang()
        self.assertEqual(viewer._lang, "zh-tw")
        self.assertEqual(viewer._lang_btn.text(), "繁中")
        self.assertNotEqual(viewer._doc_html, en_html)
        self.assertIn('data-theme="dark"', viewer._doc_html)

        viewer._toggle_lang()
        self.assertEqual(viewer._lang, "en")
        self.assertEqual(viewer._doc_html, en_html)

    def test_toggle_persists_to_rc_and_is_read_back(self) -> None:
        win = self._make_win()
        viewer = self._make_viewer(win)
        viewer.open_section("cores")
        viewer._toggle_lang()  # -> zh-tw
        win._settings.flush()

        self.assertEqual(
            _RcSettings().get("help", "stats_ref_lang", "en"), "zh-tw")

        win2 = self._make_win()
        viewer2 = self._make_viewer(win2)
        self.assertEqual(viewer2._lang, "zh-tw")
        self.assertEqual(viewer2._lang_btn.text(), "繁中")

    def test_toggle_is_a_noop_before_any_section_is_opened(self) -> None:
        win = self._make_win()
        viewer = self._make_viewer(win)
        viewer._toggle_lang()  # no pages loaded yet — must not raise/crash
        self.assertEqual(viewer._lang, "en")


if __name__ == "__main__":
    unittest.main()
