"""Desktop bug: a long tag/STI channel alias overlapped the "Xxx32 v" data-
format pill that ``_StiLabelItem.paint()`` draws in the label's corner.

Root cause #1 (collapsed row): Core View's STI-row/column label elision
(btf_viewer_pkg/scene.py ``_build_horizontal``'s "Horizontal core view"
section and ``_build_vertical``'s "Vertical core view" section) never
reserved room for that pill, unlike Task View's near-identical STI label
code a few hundred lines above it. The pill is opaque and paints on top
(z=36) of the label text (z=37) -- once alias text ran into the pill's
corner, the higher z-value text item painted over the pill instead of being
safely elided before it, and the "dropdown" pill read as if it were
transparent.

Root cause #2 (expanded row): reserving that width *unconditionally*
over-truncated the label once the row was expanded. Horizontally the pill's
column is fixed, but the pill's *row* is anchored to the bottom of
``_StiLabelItem``'s rect (``rect.bottom() - 22`` .. ``rect.bottom() - 2``);
collapsed that rect is short (``STI_ROW_H`` = 18px) so the pill sits right
where the vertically-centered label text is, but expanded it's tall
(``STI_WAVEFORM_H`` = 80px default) so the pill sits well below the label --
no overlap, so the label should get the full width back. The vertical
(column) case doesn't need this: ``label_row_h`` (the axis the pill's
height-reservation is computed against) never changes between collapsed and
expanded -- only the column's *width* does -- so one reservation covers both
states there.

Source-text presence check pinning the four call sites (Task View + Core
View, each in horizontal + vertical orientation) so they can't drift apart:
horizontal rows reserve 98px width only while collapsed (full width once
expanded); vertical columns always reserve 38px of ``label_row_h``.
"""
from __future__ import annotations

import re
import unittest
from pathlib import Path

BTF_ROOT = Path(__file__).resolve().parents[1]
SCENE = (BTF_ROOT / "btf_viewer_pkg" / "scene.py").read_text(encoding="utf-8")


class StiTagLabelPillClearanceTests(unittest.TestCase):
    def test_horizontal_sti_rows_reserve_pill_width_only_while_collapsed(self) -> None:
        # Task View ("Task columns" builder) and Core View ("Horizontal core
        # view" builder) each compute `_avail = lw - 4 - 4 if is_exp else
        # lw - 98` before eliding an expandable STI row's label: the 98px
        # reservation (leaving the 88px pill + margin clear) only applies
        # while collapsed; expanded, the pill is far below the label so the
        # full row width elides normally. Both call sites must agree.
        matches = re.findall(
            r"_avail = lw - 4 - 4 if is_exp else lw - (\d+)\n"
            r"\s*_ltxt = fm\.elidedText\(f\"\{_ind\} \{_tag_alias\(trace, channel\) or channel\}\"",
            SCENE,
        )
        self.assertEqual(
            len(matches), 2,
            "expected exactly 2 expandable-branch STI row label elisions "
            "(Task View + Core View, horizontal) -- got a different count; "
            "update this test if a new orientation/view was added",
        )
        for width in matches:
            self.assertEqual(
                width, "98",
                "an STI row's collapsed-state label elision no longer "
                "reserves the 98px format-pill clearance -- a long tag "
                "alias will run under the pill again while collapsed",
            )

    def test_vertical_sti_columns_reserve_pill_height_in_both_views(self) -> None:
        # Task View and Core View's vertical STI-column builders both elide
        # the rotated label to `label_row_h - 38` when expandable (vs. 14 for
        # non-expandable rows), leaving the pill's 20px-tall corner clear.
        # label_row_h doesn't change between collapsed/expanded (only the
        # column *width* does), so this reservation applies unconditionally.
        matches = re.findall(
            r"max\(0, label_row_h - \((\d+) if expandable else 14\)\)", SCENE)
        self.assertEqual(
            len(matches), 2,
            "expected exactly 2 expandable-aware vertical STI column label "
            "elisions (Task View + Core View) -- got a different count; "
            "update this test if a new orientation/view was added",
        )
        for height in matches:
            self.assertEqual(
                height, "38",
                "a vertical STI column's expandable-label elision no longer "
                "reserves the format-pill clearance -- a long tag alias "
                "will run under the pill again",
            )


if __name__ == "__main__":
    unittest.main()
