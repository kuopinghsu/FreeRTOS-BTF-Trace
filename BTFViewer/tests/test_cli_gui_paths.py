"""GUI argv trace paths must resolve against the launch cwd, not post-Qt cwd."""
from __future__ import annotations

import io
import os
import sys
import tempfile
import unittest
from contextlib import redirect_stderr
from pathlib import Path

BTF_ROOT = Path(__file__).resolve().parents[1]
if str(BTF_ROOT) not in sys.path:
    sys.path.insert(0, str(BTF_ROOT))

from btf_viewer_pkg._bootstrap import install  # noqa: E402

install()

from btf_viewer_pkg.cli import _cli_gui_trace_paths  # noqa: E402


class CliGuiTracePathsTest(unittest.TestCase):
    def test_relative_path_uses_base_dir_not_cwd(self) -> None:
        with tempfile.TemporaryDirectory() as launch_dir:
            trace = Path(launch_dir) / "example.btf"
            trace.write_bytes(b"#version 1.0.0\n")
            with tempfile.TemporaryDirectory() as other_dir:
                old = os.getcwd()
                try:
                    os.chdir(other_dir)
                    paths = _cli_gui_trace_paths(
                        [os.path.join(".", "example.btf")],
                        base_dir=launch_dir,
                    )
                finally:
                    os.chdir(old)
        # abspath (not Path.resolve): on macOS /var is a symlink to /private/var.
        self.assertEqual(paths, [os.path.abspath(str(trace))])

    def test_missing_file_warns_and_skips(self) -> None:
        err = io.StringIO()
        with redirect_stderr(err):
            paths = _cli_gui_trace_paths(
                [os.path.join(".", "missing.btf")],
                base_dir=tempfile.gettempdir(),
            )
        self.assertEqual(paths, [])
        self.assertIn("trace file not found", err.getvalue())


if __name__ == "__main__":
    unittest.main()
