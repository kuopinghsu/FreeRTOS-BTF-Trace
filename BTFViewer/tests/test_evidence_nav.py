"""Unit tests for Universal Evidence Navigation (Step 2)."""
from __future__ import annotations

import unittest

from btf_viewer_pkg.evidence_nav import (
    EVIDENCE_GLYPH,
    EVIDENCE_TOOLTIP,
    parse_evidence_timestamps,
    resolve_finding_evidence,
    resolve_timestamp_evidence,
)


class EvidenceNavTests(unittest.TestCase):
    def test_glyph_and_tooltip(self) -> None:
        self.assertEqual(EVIDENCE_GLYPH, "\u2197")
        self.assertIn("Scope", EVIDENCE_TOOLTIP)

    def test_parse_evidence_timestamps_units(self) -> None:
        times = parse_evidence_timestamps("at 1.5 ms and jump:2000 us")
        self.assertEqual(times, [1_500_000, 2_000_000])

    def test_parse_skips_ambiguous_bare_ints(self) -> None:
        self.assertEqual(parse_evidence_timestamps("count 42 gaps"), [])
        self.assertEqual(parse_evidence_timestamps("1234567"), [1_234_567])

    def test_resolve_finding_from_evidence_list(self) -> None:
        finding = {
            "title": "Tail",
            "task": "Worker[3]",
            "evidence": [{"time": 1000}, {"time": 5000}],
        }
        out = resolve_finding_evidence(finding, [], 0, 10_000)
        self.assertTrue(out["ok"])
        self.assertEqual(out["ns"], 5000)
        self.assertTrue(out["multi"])
        self.assertEqual(out["task"], "Worker[3]")

    def test_resolve_finding_missing(self) -> None:
        out = resolve_finding_evidence({"title": "x"}, [], 0, 0)
        self.assertFalse(out["ok"])
        self.assertIn("No locatable", out["reason"])

    def test_resolve_timestamp_clamps(self) -> None:
        out = resolve_timestamp_evidence(
            50, task="T", time_min=100, time_max=200)
        self.assertTrue(out["ok"])
        self.assertEqual(out["ns"], 100)

    def test_resolve_timestamp_invalid(self) -> None:
        out = resolve_timestamp_evidence(None)
        self.assertFalse(out["ok"])


if __name__ == "__main__":
    unittest.main()
