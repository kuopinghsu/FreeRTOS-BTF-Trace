"""Statistics Reference viewer content contract.

Every ``STATS_PINNABLE_SECTIONS`` id must resolve to a real anchor in
STATISTICS.md — otherwise a section's ⓘ icon (desktop stats_reference.py,
web StatsReferenceViewer.vue) silently opens the reference at the top
instead of jumping to the section, with no error anywhere. Nothing else
catches this: check-docs-html (scripts/ci_gate.py) only checks file
*freshness* against STATISTICS.md, not that ids inside it still line up
with config.py.
"""
from __future__ import annotations

import os
import re
import sys
import unittest
from pathlib import Path

BTF_ROOT = Path(__file__).resolve().parents[1]
if str(BTF_ROOT) not in sys.path:
    sys.path.insert(0, str(BTF_ROOT))

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from btf_viewer_pkg._bootstrap import install  # noqa: E402

install()

from btf_viewer_pkg.config import (  # noqa: E402
    STATS_PINNABLE_SECTIONS,
    STATS_SECTION_HELP,
)

STATISTICS_MD = BTF_ROOT / "STATISTICS.md"
_ANCHOR_RE = re.compile(r'<a[^>]+id=["\']statistics-([^"\']+)["\']')


class StatsReferenceAnchorTests(unittest.TestCase):
    def test_every_pinnable_section_has_a_statistics_md_anchor(self) -> None:
        text = STATISTICS_MD.read_text(encoding="utf-8")
        anchors = set(_ANCHOR_RE.findall(text))
        missing = [sid for sid in STATS_PINNABLE_SECTIONS if sid not in anchors]
        self.assertEqual(
            missing, [],
            f"STATS_PINNABLE_SECTIONS ids with no <a id=\"statistics-<id>\"> "
            f"anchor in STATISTICS.md: {missing!r}",
        )

    def test_every_pinnable_section_has_help_text(self) -> None:
        missing = [sid for sid in STATS_PINNABLE_SECTIONS if not STATS_SECTION_HELP.get(sid)]
        self.assertEqual(
            missing, [],
            f"STATS_PINNABLE_SECTIONS ids with no STATS_SECTION_HELP entry: {missing!r}",
        )


if __name__ == "__main__":
    unittest.main()
