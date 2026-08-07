"""Tests for statistics section pin helpers."""
from __future__ import annotations

import unittest

from btf_viewer_pkg import _bootstrap

_bootstrap.install()

from btf_viewer_pkg.config import (  # noqa: E402
    STATS_PINNABLE_SECTIONS,
    normalize_stats_pins,
    stats_pins_to_rc,
)


class StatsPinsTest(unittest.TestCase):
    def test_normalize_dedupes_and_filters(self) -> None:
        self.assertEqual(normalize_stats_pins("cores,bogus,tasks,cores"), ["cores", "tasks"])
        self.assertEqual(normalize_stats_pins(["tags", "tags", ""]), ["tags"])
        self.assertEqual(normalize_stats_pins(None), [])

    def test_rc_roundtrip(self) -> None:
        pins = ["migrations", "exec"]
        self.assertEqual(normalize_stats_pins(stats_pins_to_rc(pins)), pins)

    def test_catalogue_includes_common_sections(self) -> None:
        for sid in ("cores", "tasks", "tags", "migrations"):
            self.assertIn(sid, STATS_PINNABLE_SECTIONS)


if __name__ == "__main__":
    unittest.main()
