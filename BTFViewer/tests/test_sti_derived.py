"""Parity tests for fused STI post-processing (_build_sti_derived)."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

BTF_ROOT = Path(__file__).resolve().parents[1]
if str(BTF_ROOT) not in sys.path:
    sys.path.insert(0, str(BTF_ROOT))

from btf_viewer_pkg._bootstrap import install  # noqa: E402

install()

from btf_viewer_pkg.parser import (  # noqa: E402
    StiEvent,
    _build_interval_data,
    _build_interval_marker_index,
    _build_sti_derived,
    _build_tag_data,
    _is_interval_marker_channel,
    _sti_channel_sort_key,
)


def _sample_sti() -> list:
    return [
        StiEvent(100, "Core_0", "mutex", "trigger", "take 0x1"),
        StiEvent(110, "Core_0", "interval_start", "trigger", "spanA tid:1"),
        StiEvent(120, "Core_0", "tag0_event", "trigger", "42"),
        StiEvent(130, "Core_1", "interval_stop", "trigger", "spanA tid:1"),
        StiEvent(140, "Core_0", "interval_start", "trigger", "spanB"),
        StiEvent(150, "Core_0", "interval_stop", "trigger", "spanB"),
        StiEvent(160, "Core_0", "sem", "trigger", "give 0x2"),
        StiEvent(170, "Core_0", "tag0_event", "trigger", "0x10"),
    ]


class StiDerivedParityTests(unittest.TestCase):
    def test_fused_matches_separate_builders(self) -> None:
        sti = _sample_sti()

        channels_sep = sorted(
            {e.target for e in sti if not _is_interval_marker_channel(e.target)},
            key=_sti_channel_sort_key,
        )
        by_tgt_sep: dict = {}
        for ev in sti:
            by_tgt_sep.setdefault(ev.target, []).append(ev)

        inst_sep, ids_sep, by_id_sep, unmatched_sep = _build_interval_data(sti)
        markers_sep = _build_interval_marker_index(sti)
        tags_ch_sep, tags_by_sep = _build_tag_data(sti)

        (
            channels, by_tgt, inst, ids, by_id, unmatched, markers, tags_ch, tags_by,
        ) = _build_sti_derived(sti)

        self.assertEqual(channels, channels_sep)
        self.assertEqual(set(by_tgt.keys()), set(by_tgt_sep.keys()))
        for k in by_tgt:
            self.assertEqual(len(by_tgt[k]), len(by_tgt_sep[k]))
            self.assertEqual(
                [(e.time, e.target, e.note) for e in by_tgt[k]],
                [(e.time, e.target, e.note) for e in by_tgt_sep[k]],
            )

        self.assertEqual(unmatched, unmatched_sep)
        self.assertEqual(ids, ids_sep)
        self.assertEqual(len(inst), len(inst_sep))
        for a, b in zip(inst, inst_sep):
            self.assertEqual(
                (a.id, a.start_ns, a.stop_ns, a.start_core, a.stop_core, a.task_id),
                (b.id, b.start_ns, b.stop_ns, b.start_core, b.stop_core, b.task_id),
            )
        self.assertEqual(set(by_id.keys()), set(by_id_sep.keys()))

        self.assertEqual(set(markers.keys()), set(markers_sep.keys()))
        for iid in markers:
            self.assertEqual(markers[iid]["events"], markers_sep[iid]["events"])
            self.assertEqual(markers[iid]["times"], markers_sep[iid]["times"])

        self.assertEqual(tags_ch, tags_ch_sep)
        self.assertEqual(set(tags_by.keys()), set(tags_by_sep.keys()))
        for ch in tags_by:
            self.assertEqual(
                [(s.time_ns, s.value, s.core) for s in tags_by[ch]],
                [(s.time_ns, s.value, s.core) for s in tags_by_sep[ch]],
            )


if __name__ == "__main__":
    unittest.main()
