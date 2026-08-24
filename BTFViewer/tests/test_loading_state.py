"""Unit tests for Step 3 loading-state utilities."""
from __future__ import annotations

import unittest

from btf_viewer_pkg.loading_state import (
    LOADING_STAGES,
    format_loading_message,
    format_loading_pct,
    is_loading_cancellable,
    resolve_loading_stage,
)


class LoadingStateTests(unittest.TestCase):
    def test_format_loading_message_stages(self):
        self.assertEqual(format_loading_message("Reading file…"), LOADING_STAGES["reading"])
        self.assertEqual(format_loading_message("Reconstructing segments…"), LOADING_STAGES["parsing"])
        self.assertEqual(format_loading_message("Building task LOD summaries…"), LOADING_STAGES["building"])
        self.assertEqual(format_loading_message("Preparing statistics…"), LOADING_STAGES["computing"])
        self.assertEqual(format_loading_message("Building scene…"), LOADING_STAGES["building"])

    def test_format_loading_pct_rounds(self):
        self.assertEqual(format_loading_pct(0), "")
        self.assertEqual(format_loading_pct(3), "5")
        self.assertEqual(format_loading_pct(100), "100")

    def test_is_loading_cancellable(self):
        self.assertTrue(is_loading_cancellable("parse"))
        self.assertFalse(is_loading_cancellable("open"))

    def test_resolve_loading_stage(self):
        self.assertEqual(resolve_loading_stage("Indexing migrations…"), "parsing")
        self.assertEqual(resolve_loading_stage(""), "reading")


if __name__ == "__main__":
    unittest.main()
