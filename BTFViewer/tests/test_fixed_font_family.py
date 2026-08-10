"""System fixed font must be a real face — not Qt's generic Monospace alias."""
from __future__ import annotations

import os
import subprocess
import sys
import unittest
from pathlib import Path

BTF_ROOT = Path(__file__).resolve().parents[1]
if str(BTF_ROOT) not in sys.path:
    sys.path.insert(0, str(BTF_ROOT))

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from btf_viewer_pkg._bootstrap import install  # noqa: E402

install()

from PySide6.QtGui import QFont, QFontDatabase, QFontInfo  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from btf_viewer_pkg.timeline_util import (  # noqa: E402
    _get_fixed_font_family,
    _is_generic_font_family,
    _monospace_font,
)


class FixedFontFamilyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        if QApplication.instance() is None:
            QApplication([])

    def test_fixed_family_is_installed_not_generic(self) -> None:
        fam = _get_fixed_font_family()
        self.assertTrue(fam)
        self.assertFalse(_is_generic_font_family(fam))
        self.assertIn(fam, set(QFontDatabase.families()))

    def test_monospace_font_resolves_to_real_face(self) -> None:
        font = _monospace_font(8)
        self.assertEqual(font.family(), _get_fixed_font_family())
        info = QFontInfo(font)
        self.assertFalse(_is_generic_font_family(info.family()))

    def test_constructing_fixed_font_does_not_warn(self) -> None:
        env = os.environ.copy()
        env["QT_QPA_PLATFORM"] = "offscreen"
        env.pop("QT_LOGGING_RULES", None)
        env["PYTHONPATH"] = str(BTF_ROOT) + os.pathsep + env.get("PYTHONPATH", "")
        script = (
            "from PySide6.QtWidgets import QApplication\n"
            "from PySide6.QtGui import QFontInfo\n"
            "app = QApplication([])\n"
            "from btf_viewer_pkg._bootstrap import install\n"
            "install()\n"
            "from btf_viewer_pkg.timeline_util import _get_fixed_font_family, _monospace_font\n"
            "f = _monospace_font(8)\n"
            "QFontInfo(f)\n"
            "print(_get_fixed_font_family())\n"
        )
        result = subprocess.run(
            [sys.executable, "-c", script],
            capture_output=True, text=True, env=env, cwd=str(BTF_ROOT),
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotIn("missing font family", result.stderr)
        self.assertNotIn("qt.qpa.fonts", result.stderr)
        self.assertFalse(_is_generic_font_family(result.stdout.strip().splitlines()[-1]))


if __name__ == "__main__":
    unittest.main()
