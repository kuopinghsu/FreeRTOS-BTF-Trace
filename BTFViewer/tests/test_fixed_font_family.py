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
    _get_sans_font_family,
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

    def test_sans_family_is_installed_not_generic(self) -> None:
        fam = _get_sans_font_family()
        self.assertTrue(fam)
        self.assertFalse(_is_generic_font_family(fam))
        self.assertIn(fam, set(QFontDatabase.families()))

    def test_ui_font_covers_hangul_when_cjk_available(self) -> None:
        """WSL/Linux: register host CJK fonts so Korean AI text is not tofu."""
        from PySide6.QtGui import QRawFont
        from btf_viewer_pkg.config import (
            _application_ui_font,
            _cjk_capable_ui_family,
            _ensure_cjk_application_fonts,
        )

        _ensure_cjk_application_fonts()
        cjk = _cjk_capable_ui_family()
        if cjk is None and not os.path.isfile("/mnt/c/Windows/Fonts/malgun.ttf"):
            self.skipTest("no Hangul-capable font available")
        self.assertIsNotNone(cjk)
        font = _application_ui_font(10)
        gids = QRawFont.fromFont(font).glyphIndexesForString("한국어")
        self.assertTrue(gids)
        self.assertTrue(all(int(g) > 0 for g in gids), gids)
        sans = _get_sans_font_family()
        self.assertTrue(
            all(int(g) > 0 for g in QRawFont.fromFont(QFont(sans)).glyphIndexesForString("한")),
            sans,
        )

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

    def test_mermaid_and_gauge_svg_skip_css_generic_fonts(self) -> None:
        from btf_viewer_pkg.ai_mermaid import mermaid_to_svg  # noqa: WPS433
        from btf_viewer_pkg.ai_tools import AI_MERMAID_SEQUENCE_EXAMPLE  # noqa: WPS433
        from btf_viewer_pkg.stats import _load_balance_gauge_svg  # noqa: WPS433

        src = AI_MERMAID_SEQUENCE_EXAMPLE.replace("```mermaid", "").replace("```", "").strip()
        svg = mermaid_to_svg(src)
        self.assertNotIn("sans-serif", svg.lower())
        self.assertIn(f'font-family="{_get_sans_font_family()}"', svg)
        gauge = _load_balance_gauge_svg({
            "score": 82, "gini": 0.18, "stddev": 12, "zone": "ok",
        })
        self.assertNotIn("sans-serif", gauge.lower())
        self.assertNotRegex(gauge, r'font-family="monospace"')
        self.assertIn(f'font-family="{_get_sans_font_family()}"', gauge)
        self.assertIn(f'font-family="{_get_fixed_font_family()}"', gauge)
        self.assertNotIn('width="100%"', gauge)
        self.assertNotIn('height="100%"', gauge)


if __name__ == "__main__":
    unittest.main()
