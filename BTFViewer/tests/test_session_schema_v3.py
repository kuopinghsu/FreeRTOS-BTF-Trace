"""TODO.md — Session Schema v3 revision.

Bump the portable Session / .btfw view-state schema from v2 to v3 and drop
the unused ``compareScopeToCursors`` field, while keeping v1/v2 Session
files and .btfw workspaces loadable.

Covers:
  - SESSION_PORTABLE_VERSION == 3 on both platforms.
  - PORTABLE_VIEW_STATE_KEYS / buildPortableSession's field set no longer
    include compareScopeToCursors (14 canonical fields, not 15).
  - New Desktop Session/.btfw exports carry version 3 and omit the field.
  - v1 and v2 Session import still works, including a v2 payload that still
    carries the now-removed field (simply ignored, not fatal).
  - Runtime source has zero remaining compareScopeToCursors references
    (the TODO's own "search regression gate").
"""
from __future__ import annotations

import json
import os
import re
import sys
import tempfile
import unittest
import zipfile
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
)
from btf_viewer_pkg.mainwindow import MainWindow  # noqa: E402
from btf_viewer_pkg.parser import _parse_btf  # noqa: E402
from btf_viewer_pkg.workspace import open_workspace  # noqa: E402

EVIDENCE_JS = (BTF_ROOT / "web" / "src" / "utils" / "sessionPortable.js").read_text(encoding="utf-8")
EXAMPLE_2CORE = BTF_ROOT.parent / "tracedata" / "example-2cores.btf.gz"


def _destroy(win) -> None:
    try:
        win.close()
        win.deleteLater()
    except Exception:
        pass


class SchemaVersionBumpTests(unittest.TestCase):
    def test_desktop_version_is_3(self) -> None:
        self.assertEqual(SESSION_PORTABLE_VERSION, 3)

    def test_web_version_is_3(self) -> None:
        self.assertRegex(EVIDENCE_JS, r"SESSION_PORTABLE_VERSION\s*=\s*3\b")

    def test_canonical_keys_no_longer_include_compare_scope(self) -> None:
        self.assertNotIn("compareScopeToCursors", PORTABLE_VIEW_STATE_KEYS)
        self.assertEqual(len(PORTABLE_VIEW_STATE_KEYS), 14)

    def test_web_builder_no_longer_destructures_compare_scope(self) -> None:
        self.assertNotIn("compareScopeToCursors", EVIDENCE_JS)


class SearchRegressionGateTests(unittest.TestCase):
    """TODO.md's own "grep -R compareScopeToCursors" gate: zero matches in
    runtime source once the revision is complete."""

    def test_no_runtime_references_remain(self) -> None:
        hits = []
        for pattern in ("btf_viewer_pkg/*.py", "web/src/**/*.js", "web/src/**/*.vue"):
            for path in BTF_ROOT.glob(pattern):
                text = path.read_text(encoding="utf-8", errors="ignore")
                if "compareScopeToCursors" in text:
                    hits.append(str(path.relative_to(BTF_ROOT)))
        self.assertEqual(hits, [], f"compareScopeToCursors still referenced in: {hits}")


class DesktopSessionExportGuiTests(unittest.TestCase):
    _app = None

    @classmethod
    def setUpClass(cls) -> None:
        cls._app = QApplication.instance() or QApplication([])

    def setUp(self) -> None:
        if not EXAMPLE_2CORE.is_file():
            self.skipTest(f"missing {EXAMPLE_2CORE}")
        self.trace = _parse_btf(str(EXAMPLE_2CORE))
        self.win = MainWindow()
        self.addCleanup(_destroy, self.win)
        self.tab = self.win._add_trace_tab(str(EXAMPLE_2CORE), self.trace)
        self.tab.view.load_trace(self.trace)
        self.win._tab_widget.setCurrentIndex(0)
        for _ in range(3):
            self._app.processEvents()

    def test_new_session_payload_is_v3_without_compare_scope(self) -> None:
        payload = self.win._build_portable_session_payload()
        self.assertEqual(payload["version"], 3)
        self.assertNotIn("compareScopeToCursors", payload)
        for key in PORTABLE_VIEW_STATE_KEYS:
            self.assertIn(key, payload, key)

    def test_v1_session_still_imports(self) -> None:
        try:
            self.win._apply_portable_session_payload({"version": 1})
        except ValueError as exc:  # pragma: no cover - failure message only
            self.fail(f"v1 session import raised: {exc!r}")

    def test_v2_session_with_legacy_field_still_imports(self) -> None:
        # A real old v2 export may still carry the now-removed field --
        # it must be silently ignored, not rejected.
        try:
            self.win._apply_portable_session_payload({
                "version": 2,
                "compareScopeToCursors": True,
            })
        except ValueError as exc:  # pragma: no cover - failure message only
            self.fail(f"v2 session import with legacy field raised: {exc!r}")

    def test_v3_session_imports(self) -> None:
        try:
            self.win._apply_portable_session_payload({"version": 3})
        except ValueError as exc:  # pragma: no cover - failure message only
            self.fail(f"v3 session import raised: {exc!r}")

    def test_unsupported_version_still_rejected(self) -> None:
        with self.assertRaises(ValueError):
            self.win._apply_portable_session_payload({"version": 99})

    def test_new_workspace_state_is_v3_without_compare_scope(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            out_path = str(Path(tmp) / "w.btfw")
            with patch(
                "btf_viewer_pkg.mainwindow.QFileDialog.getSaveFileName",
                return_value=(out_path, ""),
            ):
                self.win._run_workspace_export(embed=True)
            self.assertTrue(Path(out_path).is_file())
            with zipfile.ZipFile(out_path) as zf:
                view = json.loads(zf.read("state/view.json"))
            self.assertEqual(view["version"], 3)
            self.assertNotIn("compareScopeToCursors", view)

            ws = open_workspace(out_path)
            self.assertEqual(ws["view_state"]["version"], 3)


if __name__ == "__main__":
    unittest.main()
