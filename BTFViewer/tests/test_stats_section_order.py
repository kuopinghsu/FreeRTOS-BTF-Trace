"""Resetting statistics section order must not leave the scroll pad mid-list."""
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

from PySide6.QtWidgets import QApplication, QWidget  # noqa: E402

from btf_viewer_pkg.stats import _StatsPanel  # noqa: E402


def _app() -> QApplication:
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


class StatsSectionOrderLayoutTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        _app()

    def _layout_widgets(self, panel: _StatsPanel) -> list:
        out = []
        for i in range(panel._ilay.count()):
            item = panel._ilay.itemAt(i)
            w = item.widget() if item is not None else None
            if w is not None:
                out.append(w)
        return out

    def test_apply_order_keeps_scroll_tail_last(self) -> None:
        """The viewport-tall pad must stay after every section, not between them."""
        panel = _StatsPanel()
        while panel._ilay.count():
            item = panel._ilay.takeAt(0)
            w = item.widget() if item is not None else None
            if w is not None:
                w.setParent(None)
        panel._section_seps.clear()
        panel._section_header_rows.clear()
        panel._section_bodies.clear()

        def _mount(sid: str) -> None:
            sep = QWidget()
            hdr = QWidget()
            body = QWidget()
            sep.setObjectName(f"sep_{sid}")
            hdr.setObjectName(f"hdr_{sid}")
            body.setObjectName(f"body_{sid}")
            panel._section_seps[sid] = sep
            panel._section_header_rows[sid] = hdr
            panel._section_bodies[sid] = body
            panel._ilay.addWidget(sep)
            panel._ilay.addWidget(hdr)
            panel._ilay.addWidget(body)

        _mount("exec")
        _mount("block")
        tail = QWidget()
        tail.setObjectName("stats_scroll_tail")
        tail.setFixedHeight(400)
        panel._ilay.addWidget(tail)
        panel._scroll_tail = tail
        panel._section_order = ["block", "exec"]

        panel._apply_section_layout_order()

        widgets = self._layout_widgets(panel)
        self.assertIs(widgets[-1], tail)
        self.assertNotIn(tail, widgets[:-1])
        self.assertEqual(
            [w.objectName() for w in widgets[:-1]],
            ["sep_block", "hdr_block", "body_block",
             "sep_exec", "hdr_exec", "body_exec"],
        )

        panel._reset_section_order()
        widgets = self._layout_widgets(panel)
        self.assertIs(widgets[-1], tail)
        self.assertNotIn(tail, widgets[:-1])
        self.assertEqual(
            [w.objectName() for w in widgets[:-1]],
            ["sep_exec", "hdr_exec", "body_exec",
             "sep_block", "hdr_block", "body_block"],
        )


if __name__ == "__main__":
    unittest.main()
