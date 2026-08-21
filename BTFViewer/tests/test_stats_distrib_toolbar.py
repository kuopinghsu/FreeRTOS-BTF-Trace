"""Distribution Explorer toolbar must stay visible in a short stats dock."""
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

from PySide6.QtWidgets import QApplication, QPushButton  # noqa: E402

from btf_viewer_pkg.parser import _parse_btf  # noqa: E402
from btf_viewer_pkg.stats import _StatsPanel  # noqa: E402

TRACE = Path(__file__).resolve().parents[2] / "tracedata" / "example-2cores.btf.gz"
FALLBACK = BTF_ROOT / "tests" / "ai" / "response_vs_blocking.btf"


def _app() -> QApplication:
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


class DistribToolbarVisibilityTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        _app()

    def test_open_histogram_and_query_ai_keep_nonzero_height(self) -> None:
        path = TRACE if TRACE.is_file() else FALLBACK
        if not path.is_file():
            self.skipTest(f"missing fixture {TRACE} / {FALLBACK}")
        panel = _StatsPanel()
        panel.resize(320, 480)
        panel.show()
        panel.rebuild(_parse_btf(str(path)))
        # Keep only Distribution Explorer expanded so the dock is height-starved.
        for sid in list(panel._section_collapsed):
            panel._set_section_collapsed(sid, True)
        panel._set_section_collapsed("distrib", False)
        QApplication.processEvents()

        body = panel._section_bodies.get("distrib")
        self.assertIsNotNone(body)
        labels = {b.text(): b for b in body.findChildren(QPushButton)}
        self.assertIn("Open histogram", labels)
        self.assertIn("Query with AI…", labels)
        for name in ("Open histogram", "Query with AI…"):
            btn = labels[name]
            self.assertGreaterEqual(
                btn.height(), 18,
                f"{name} crushed to height {btn.height()} (geo={btn.geometry()})")
            self.assertTrue(btn.isVisible())


if __name__ == "__main__":
    unittest.main()
