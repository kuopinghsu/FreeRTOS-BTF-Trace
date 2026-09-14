from __future__ import annotations

import math
import os
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace

BTF_ROOT = Path(__file__).resolve().parents[1]
if str(BTF_ROOT) not in sys.path:
    sys.path.insert(0, str(BTF_ROOT))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from btf_viewer_pkg._bootstrap import install  # noqa: E402
install()
from btf_viewer_pkg import parser as P  # noqa: E402


class TestTagRepresentation(unittest.TestCase):
    def test_same_word_has_four_representations(self) -> None:
        self.assertEqual(P._interpret_tag_value("-1", "uint32"), 0xFFFFFFFF)
        self.assertEqual(P._interpret_tag_value("4294967295", "int32"), -1)
        self.assertEqual(P._interpret_tag_value("1065353216", "float32"), 1.0)
        self.assertEqual(P._interpret_tag_value("255", "log2-uint32"), 8.0)

    def test_wide_sparse_range_recommends_log2(self) -> None:
        samples = [
            P.TagSample("tag3_event", i, float(value), "Core_0", str(value), value)
            for i, value in enumerate((1, 1024, 1048576))
        ]
        trace = SimpleNamespace(
            tag_channels=["tag3_event"],
            tag_samples_by_channel={"tag3_event": samples},
            tag_representations={},
        )
        self.assertEqual(P._recommend_tag_representation(trace, "tag3_event"), "log2-uint32")
        values = [point[1] for point in P._tag_plot_points(trace, "tag3_event")]
        self.assertEqual(values, [1.0, math.log2(1025), math.log2(1048577)])

    def test_manual_float32_override_drives_stats(self) -> None:
        words = (1065353216, 1073741824)
        samples = [
            P.TagSample("tag0_event", i, float(word), "Core_0", str(word), word)
            for i, word in enumerate(words)
        ]
        trace = SimpleNamespace(
            tag_channels=["tag0_event"],
            tag_samples_by_channel={"tag0_event": samples},
            tag_representations={"tag0_event": "float32"},
        )
        row = P._tag_stats_rows(trace)[0]
        self.assertEqual(row[3], "1")
        self.assertEqual(row[5], "2")


if __name__ == "__main__":
    unittest.main()
