"""Unit tests for QPA platform startup handling (no Qt instance needed)."""
from __future__ import annotations

import contextlib
import io
import os
import sys
import unittest
from pathlib import Path
from unittest import mock

BTF_ROOT = Path(__file__).resolve().parents[1]
if str(BTF_ROOT) not in sys.path:
    sys.path.insert(0, str(BTF_ROOT))

from btf_viewer_pkg.platform import (  # noqa: E402
    _HEADLESS_CLI_COMMANDS,
    _configure_qt_startup,
    _headless_cli_invocation,
)

class HeadlessInvocationTests(unittest.TestCase):
    def test_cli_subcommand_is_headless(self) -> None:
        self.assertTrue(_headless_cli_invocation(["btf_viewer.py", "snapshot", "t.btf"]))
        self.assertTrue(_headless_cli_invocation(["btf_viewer.py", "report", "t.btf"]))

    def test_gui_launch_is_not_headless(self) -> None:
        self.assertFalse(_headless_cli_invocation(["btf_viewer.py"]))
        self.assertFalse(_headless_cli_invocation(["btf_viewer.py", "trace.btf"]))

    def test_command_set_matches_cli(self) -> None:
        from btf_viewer_pkg.cli import _CLI_COMMANDS

        self.assertEqual(set(_CLI_COMMANDS), set(_HEADLESS_CLI_COMMANDS))

class MacosQpaOverrideTests(unittest.TestCase):
    def setUp(self) -> None:
        patcher = mock.patch.dict(os.environ, {"QT_QPA_PLATFORM": "offscreen"})
        patcher.start()
        self.addCleanup(patcher.stop)
        darwin = mock.patch.object(sys, "platform", "darwin")
        darwin.start()
        self.addCleanup(darwin.stop)

    def test_cli_subcommand_keeps_offscreen(self) -> None:
        """cocoa aborts in _RegisterApplication when LaunchServices is blocked."""
        _configure_qt_startup(["btf_viewer.py", "snapshot", "t.btf", "-o", "o.png"])
        self.assertEqual(os.environ.get("QT_QPA_PLATFORM"), "offscreen")

    def test_gui_launch_drops_offscreen(self) -> None:
        with contextlib.redirect_stderr(io.StringIO()) as err:
            _configure_qt_startup(["btf_viewer.py", "trace.btf"])
        self.assertNotIn("QT_QPA_PLATFORM", os.environ)
        self.assertIn("offscreen", err.getvalue())

if __name__ == "__main__":
    unittest.main()
