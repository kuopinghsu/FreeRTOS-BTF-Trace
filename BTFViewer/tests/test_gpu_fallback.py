"""Headless / GPU-less software-GL fallback selected before the first PySide6 import.

The block lives inline (it must run before Qt loads) in two places that are
kept in sync: ``btf_viewer_pkg/_imports.py`` and the ``SHARED_IMPORTS`` string
in ``scripts/bundle_viewer.py``.
"""
from __future__ import annotations

import re
import sys
import types
import unittest
from pathlib import Path

BTF_ROOT = Path(__file__).resolve().parents[1]

_MARKER = "Headless / GPU-less software-GL fallback"
_END = "import argparse"


def _extract_block(text: str) -> str:
    lines = text.splitlines()
    start = next(i for i, ln in enumerate(lines) if _MARKER in ln)
    # walk back to the first comment line of the block
    while start > 0 and lines[start - 1].lstrip().startswith("#"):
        start -= 1
    end = next(i for i in range(start, len(lines)) if lines[i].strip() == _END)
    return "\n".join(lines[start:end]).rstrip() + "\n"


def _dev_block() -> str:
    return _extract_block((BTF_ROOT / "btf_viewer_pkg" / "_imports.py").read_text("utf-8"))


def _bundle_block() -> str:
    src = (BTF_ROOT / "scripts" / "bundle_viewer.py").read_text("utf-8")
    shared = re.search(r'SHARED_IMPORTS = """\\\n(.*?)"""', src, re.S).group(1)
    return _extract_block(shared)


class ParityTest(unittest.TestCase):
    def test_dev_and_bundle_blocks_match(self):
        self.assertEqual(_dev_block(), _bundle_block())


class BehaviourTest(unittest.TestCase):
    def _run(self, *, platform: str, dri_names, environ: dict) -> dict:
        env = dict(environ)
        fake_os = types.SimpleNamespace(
            environ=env,
            listdir=lambda p: (dri_names if dri_names is not None else _raise()),
        )
        fake_sys = types.SimpleNamespace(platform=platform)
        ns = {"os": fake_os, "sys": fake_sys}
        exec(compile(_dev_block(), "<gpu-fallback>", "exec"), ns)  # noqa: S102
        return env

    def test_activates_when_no_render_node(self):
        env = self._run(platform="linux", dri_names=["card0", "by-path"], environ={})
        self.assertEqual(env["LIBGL_ALWAYS_SOFTWARE"], "1")
        self.assertIn("--disable-gpu", env["QTWEBENGINE_CHROMIUM_FLAGS"])
        self.assertIn("--disable-gpu-compositing", env["QTWEBENGINE_CHROMIUM_FLAGS"])

    def test_noop_with_a_real_render_node(self):
        env = self._run(platform="linux", dri_names=["card0", "renderD128"], environ={})
        self.assertNotIn("LIBGL_ALWAYS_SOFTWARE", env)
        self.assertNotIn("QTWEBENGINE_CHROMIUM_FLAGS", env)

    def test_noop_when_no_dev_dri(self):
        env = self._run(platform="linux", dri_names=[], environ={})
        self.assertEqual(env["LIBGL_ALWAYS_SOFTWARE"], "1")  # empty dir == no GPU

    def test_noop_on_non_linux(self):
        for plat in ("darwin", "win32"):
            env = self._run(platform=plat, dri_names=["card0"], environ={})
            self.assertEqual(env, {})

    def test_opt_out_env_var(self):
        env = self._run(platform="linux", dri_names=["card0"],
                        environ={"BTFVIEWER_NO_GL_FALLBACK": "1"})
        self.assertEqual(env, {"BTFVIEWER_NO_GL_FALLBACK": "1"})

    def test_explicit_values_are_respected(self):
        env = self._run(
            platform="linux", dri_names=["card0"],
            environ={"LIBGL_ALWAYS_SOFTWARE": "0",
                     "QTWEBENGINE_CHROMIUM_FLAGS": "--foo"})
        self.assertEqual(env["LIBGL_ALWAYS_SOFTWARE"], "0")   # setdefault kept it
        self.assertIn("--foo", env["QTWEBENGINE_CHROMIUM_FLAGS"])
        self.assertIn("--disable-gpu", env["QTWEBENGINE_CHROMIUM_FLAGS"])

    def test_flags_not_duplicated(self):
        env = self._run(
            platform="linux", dri_names=["card0"],
            environ={"QTWEBENGINE_CHROMIUM_FLAGS": "--disable-gpu"})
        flags = env["QTWEBENGINE_CHROMIUM_FLAGS"].split()
        self.assertEqual(flags.count("--disable-gpu"), 1)
        self.assertEqual(flags.count("--disable-gpu-compositing"), 1)


def _raise():
    raise OSError("no /dev/dri")


if __name__ == "__main__":
    unittest.main()
