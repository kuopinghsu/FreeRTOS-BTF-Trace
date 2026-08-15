"""Desktop ↔ web statistics parity (demo_8cores C1–C2 window).

Shared golden: tests/fixtures/demo_8cores-cursor-stats-golden.json
(the same file is asserted from web/tests/statsWebParity.test.js).

Regenerate after an intentional stats-algorithm change::

    STATS_PARITY_WRITE_GOLDEN=1 python3 -m unittest tests.test_stats_web_parity -v
"""
from __future__ import annotations

import json
import os
import sys
import unittest
from pathlib import Path

BTF_ROOT = Path(__file__).resolve().parents[1]
if str(BTF_ROOT) not in sys.path:
    sys.path.insert(0, str(BTF_ROOT))

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from btf_viewer_pkg._bootstrap import install  # noqa: E402

install()

from btf_viewer_pkg.parser import (  # noqa: E402
    _blocking_time_samples,
    _exec_slice_samples,
    _is_idle_task_name,
    _parse_btf,
    _parse_task_name,
    _priority_stats_rows,
    _scheduling_stats,
    _seg_overlaps_range,
    _task_display_name,
    _task_lifecycle_rows,
)
from btf_viewer_pkg.timeline_util import _from_ns  # noqa: E402

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "demo_8cores-cursor-stats-golden.json"
TRACE = BTF_ROOT / "demos" / "demo_8cores" / "demo_8cores.btf.gz"
DEMO_XML = BTF_ROOT / "demos" / "demo_8cores" / "demo_8cores.xml"

CURSOR_LO_S = 3.085
CURSOR_HI_S = 3.310


def _sample_summary(samples: list) -> dict:
    return {
        "n": len(samples),
        "min": min(samples),
        "max": max(samples),
        "sum": int(sum(samples)),
    }


def cursor_stats_snapshot(trace, lo: int, hi: int) -> dict:
    ctx, gaps = _scheduling_stats(trace, lo, hi)

    lifecycle = []
    for (
        _mk, label, create_ns, delete_ns, sus, res, alive, events, runs,
    ) in _task_lifecycle_rows(trace, lo, hi):
        lifecycle.append({
            "label": label,
            "createNs": create_ns,
            "deleteNs": delete_ns,
            "suspendCount": sus,
            "resumeCount": res,
            "aliveNs": alive,
            "eventCount": events,
            "runCount": runs,
        })
    lifecycle.sort(key=lambda r: r["label"])

    priority = []
    for (
        _mk, label, base, peak, n_ep, _fmt, pattern, total_ns,
    ) in _priority_stats_rows(trace, lo, hi):
        priority.append({
            "label": label,
            "basePri": int(base),
            "peakPri": int(peak),
            "episodeCount": int(n_ep),
            "totalBoostNs": int(total_ns),
            "pattern": pattern,
        })
    priority.sort(key=lambda r: r["label"])

    block = []
    exec_rows = []
    for mk, segs in trace.seg_map_by_merge_key.items():
        raw = trace.task_repr.get(mk, mk)
        _, _, tname = _parse_task_name(raw)
        if _is_idle_task_name(tname) or tname == "TICK":
            continue
        label = _task_display_name(raw)
        bs = _blocking_time_samples(segs, lo, hi)
        if bs:
            block.append({"label": label, **_sample_summary(bs)})
        es = _exec_slice_samples(segs, lo, hi)
        if es:
            exec_rows.append({"label": label, **_sample_summary(es)})
    block.sort(key=lambda r: r["label"])
    exec_rows.sort(key=lambda r: r["label"])

    task_count = sum(
        1 for segs in trace.seg_map_by_merge_key.values()
        if any(_seg_overlaps_range(s, lo, hi) for s in segs)
    )
    seg_count = sum(
        1 for segs in trace.seg_map_by_merge_key.values()
        for s in segs if _seg_overlaps_range(s, lo, hi)
    )

    return {
        "trace": "demo_8cores.btf.gz",
        "timeScale": trace.time_scale,
        "lo": lo,
        "hi": hi,
        "taskCount": task_count,
        "segCount": seg_count,
        "scheduling": {
            "contextSwitches": int(ctx),
            "gapCount": len(gaps),
            "gapSum": int(sum(gaps)),
        },
        "priority": priority,
        "lifecycle": lifecycle,
        "block": block,
        "exec": exec_rows,
    }


class TestStatsWebParity(unittest.TestCase):
    def test_overlap_helpers_and_lifecycle_count_match_web(self) -> None:
        """Scoped runCount / range predicates stay aligned with the web helpers."""
        parser = (BTF_ROOT / "btf_viewer_pkg" / "parser.py").read_text(
            encoding="utf-8")
        life_js = (BTF_ROOT / "web" / "src" / "utils" / "lifecycleAnalysis.js").read_text(
            encoding="utf-8")
        range_js = (BTF_ROOT / "web" / "src" / "utils" / "statsRange.js").read_text(
            encoding="utf-8")
        pri_js = (BTF_ROOT / "web" / "src" / "utils" / "priorityAnalysis.js").read_text(
            encoding="utf-8")
        panel = (BTF_ROOT / "web" / "src" / "components" / "StatisticsPanel.vue").read_text(
            encoding="utf-8")

        self.assertIn(
            "run_count = sum(1 for s in segs if _seg_overlaps_range(s, lo, hi))",
            parser,
        )
        self.assertIn("return seg.end > lo and seg.start < hi", parser)
        self.assertIn(
            "return seg.start >= lo and seg.end <= hi", parser)
        self.assertIn(
            "return ep.stop_ns > lo and ep.start_ns < hi", parser)

        self.assertIn("segOverlapsRange(s, lo, hi)", life_js)
        self.assertNotIn("segs.reduce", life_js)
        self.assertIn("return seg.end > lo && seg.start < hi", range_js)
        self.assertIn("return seg.start >= lo && seg.end <= hi", range_js)
        self.assertIn("ep.stopNs > lo && ep.startNs < hi", pri_js)

        # Always-visible section + empty hint (same as Desktop).
        self.assertIn('v-if="lifecycleStats.length === 0"', panel)
        self.assertIn("tr.segByMergeKey", panel)
        self.assertIn("buildTaskLifecycleRows", panel)

    def test_demo_xml_inversion_window_matches_golden_bounds(self) -> None:
        xml = DEMO_XML.read_text(encoding="utf-8")
        self.assertIn('times="3.085,3.310"', xml)
        self.assertIn('unit="s"', xml)
        self.assertIn('limit="true"', xml)

    def test_demo_8cores_cursor_stats_match_golden(self) -> None:
        if not TRACE.is_file():
            self.skipTest(f"missing trace fixture: {TRACE}")
        if not FIXTURE.is_file():
            self.skipTest(f"missing golden fixture: {FIXTURE}")

        expected = json.loads(FIXTURE.read_text(encoding="utf-8"))
        trace = _parse_btf(str(TRACE))
        lo = int(round(_from_ns(CURSOR_LO_S * 1_000_000_000.0, trace.time_scale)))
        hi = int(round(_from_ns(CURSOR_HI_S * 1_000_000_000.0, trace.time_scale)))
        actual = cursor_stats_snapshot(trace, lo, hi)

        if os.environ.get("STATS_PARITY_WRITE_GOLDEN") == "1":
            FIXTURE.write_text(
                json.dumps(actual, indent=2) + "\n", encoding="utf-8")

        self.assertEqual(actual["lo"], expected["lo"])
        self.assertEqual(actual["hi"], expected["hi"])
        self.assertEqual(actual, expected)


if __name__ == "__main__":
    unittest.main()
