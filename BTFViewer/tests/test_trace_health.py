"""Unit + regression tests for deterministic structural trace-health checks.

Covers ``btf_viewer_pkg.trace_health`` and the HTML card in
``btf_viewer_pkg.stats_html``. Parity with ``web/tests/traceHealth.test.js``.
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path
from types import SimpleNamespace

BTF_ROOT = Path(__file__).resolve().parents[1]
if str(BTF_ROOT) not in sys.path:
    sys.path.insert(0, str(BTF_ROOT))

from btf_viewer_pkg.stats_html import html_trace_health_card  # noqa: E402
from btf_viewer_pkg.trace_health import (  # noqa: E402
    CHECK_CAPTURE_TRUNCATION,
    CHECK_CORE_INTERVAL_OVERLAP,
    CHECK_EMPTY_TRACE,
    CHECK_LONG_GAP,
    CHECK_METRIC_PREREQUISITES,
    CHECK_MISSING_TASK_IDENTITY,
    CHECK_SYNC_PAIRING,
    CHECK_TIMESTAMP_SKIPS,
    CHECK_TIMESTAMP_UNITS,
    CHECK_UNKNOWN_CORE,
    CHECK_UNMATCHED_INTERVALS,
    STATUS_CAUTION,
    STATUS_INSUFFICIENT,
    STATUS_PASS,
    build_trace_health_result,
    trace_health_status_label,
    trace_health_summary,
)

FIXTURES = BTF_ROOT / "tests" / "fixtures" / "health"


def _seg(start, end, core="Core_0"):
    return SimpleNamespace(start=start, end=end, core=core)


def _trace(**over):
    base = dict(
        segments=[],
        sti_events=[],
        meta={},
        time_scale="us",
        core_names=["Core_0", "Core_1"],
        task_repr={},
        tasks=[],
        tick_sti_times=[10, 20, 30],
        sti_channels=["mutex", "interval_start"],
        interval_unmatched_starts=0,
        interval_ids=["1"],
        sync_issues=[],
        has_sync_object_instrumentation=True,
        has_priority_instrumentation=True,
        time_min=0,
        time_max=1000,
    )
    base.update(over)
    return SimpleNamespace(**base)


def _ids(result):
    return {c["id"] for c in result["checks"]}


def _by_id(result, cid):
    return next(c for c in result["checks"] if c["id"] == cid)


class StructuralCheckTests(unittest.TestCase):
    def test_none_trace_is_insufficient(self):
        r = build_trace_health_result(None)
        self.assertEqual(r["status"], STATUS_INSUFFICIENT)
        self.assertEqual(_ids(r), {CHECK_EMPTY_TRACE})

    def test_empty_trace_is_insufficient_and_short_circuits(self):
        r = build_trace_health_result(_trace(segments=[], sti_events=[]))
        self.assertEqual(r["status"], STATUS_INSUFFICIENT)
        # empty_trace suppresses every other check
        self.assertEqual(_ids(r), {CHECK_EMPTY_TRACE})

    def test_clean_trace_passes(self):
        r = build_trace_health_result(_trace(
            segments=[_seg(0, 10, "Core_0"), _seg(10, 20, "Core_1")],
        ))
        self.assertEqual(r["status"], STATUS_PASS)
        self.assertEqual(r["issue_count"], 0)
        self.assertEqual(r["checks"], [])

    def test_core_interval_overlap_warns_then_errors_by_ratio(self):
        # 1 contained overlap in 200 slices -> 0.5% -> warning
        segs = [_seg(i * 10, i * 10 + 10, "Core_0") for i in range(200)]
        segs.append(_seg(2, 8, "Core_0"))  # sits inside slice 0, no cascade
        r = build_trace_health_result(_trace(segments=segs))
        self.assertEqual(_by_id(r, CHECK_CORE_INTERVAL_OVERLAP)["severity"], "warning")
        self.assertEqual(r["status"], STATUS_CAUTION)

        # many overlaps -> ratio above threshold -> error -> insufficient
        segs2 = [_seg(0, 100, "Core_0"), _seg(10, 110, "Core_0"),
                 _seg(20, 120, "Core_0"), _seg(30, 130, "Core_0")]
        r2 = build_trace_health_result(_trace(segments=segs2))
        chk = _by_id(r2, CHECK_CORE_INTERVAL_OVERLAP)
        self.assertEqual(chk["severity"], "error")
        self.assertEqual(r2["status"], STATUS_INSUFFICIENT)
        self.assertEqual(chk["affected_entities"], ["Core_0"])
        self.assertIsNotNone(chk["affected_range"])
        self.assertTrue(chk["evidence_refs"])

    def test_touching_segments_are_not_overlaps(self):
        r = build_trace_health_result(_trace(
            segments=[_seg(0, 10, "Core_0"), _seg(10, 20, "Core_0")],
        ))
        self.assertNotIn(CHECK_CORE_INTERVAL_OVERLAP, _ids(r))

    def test_unknown_core_identifier(self):
        r = build_trace_health_result(_trace(
            segments=[_seg(0, 10, "Core_0")],
            core_names=["Core_0", "Core_99", "weird"],
        ))
        chk = _by_id(r, CHECK_UNKNOWN_CORE)
        self.assertEqual(chk["severity"], "warning")
        self.assertIn("Core_99", chk["affected_entities"])
        self.assertIn("weird", chk["affected_entities"])

    def test_missing_task_identity_from_overflow_and_placeholder(self):
        r = build_trace_health_result(_trace(
            segments=[_seg(0, 10, "Core_0")],
            meta={"taskTableOverflow": "true"},
            task_repr={"a": "[0/0007]", "b": "Runner", "c": ""},
        ))
        chk = _by_id(r, CHECK_MISSING_TASK_IDENTITY)
        self.assertEqual(chk["severity"], "warning")
        self.assertIn("overflow", chk["summary"].lower())

    def test_unmatched_intervals(self):
        r = build_trace_health_result(_trace(
            segments=[_seg(0, 10, "Core_0")],
            interval_unmatched_starts=4,
        ))
        self.assertEqual(_by_id(r, CHECK_UNMATCHED_INTERVALS)["severity"], "warning")

    def test_sync_pairing_issues_carry_evidence(self):
        r = build_trace_health_result(_trace(
            segments=[_seg(0, 10, "Core_0")],
            sync_issues=[
                {"kind": "ORPHAN_GIVE", "time_ns": 1234},
                {"kind": "UNMATCHED_TAKE", "time_ns": 5678},
            ],
        ), format_ns=lambda ns: f"{ns} u")
        chk = _by_id(r, CHECK_SYNC_PAIRING)
        self.assertEqual(chk["severity"], "warning")
        self.assertIn("ORPHAN_GIVE @ 1234 u", chk["evidence_refs"])

    def test_capture_truncation_folds_metadata_warnings(self):
        r = build_trace_health_result(_trace(
            segments=[_seg(0, 10, "Core_0")],
            meta={"ringOverflow": "true", "truncated": "true"},
        ))
        chk = _by_id(r, CHECK_CAPTURE_TRUNCATION)
        self.assertEqual(chk["severity"], "warning")
        self.assertIn("ring buffer overflow", chk["summary"])

    def test_unknown_timestamp_unit_is_error(self):
        r = build_trace_health_result(_trace(
            segments=[_seg(0, 10, "Core_0")],
            time_scale="furlongs",
        ))
        self.assertEqual(_by_id(r, CHECK_TIMESTAMP_UNITS)["severity"], "error")
        self.assertEqual(r["status"], STATUS_INSUFFICIENT)

    def test_timestamp_skips_from_meta(self):
        for key in ("_skipped_lines", "skippedLines"):
            r = build_trace_health_result(_trace(
                segments=[_seg(0, 10, "Core_0")],
                meta={key: "7"},
            ))
            self.assertEqual(_by_id(r, CHECK_TIMESTAMP_SKIPS)["severity"], "warning")

    def test_long_data_gap_is_info_with_range(self):
        segs = [_seg(0, 10, "Core_0"), _seg(900, 1000, "Core_0")]
        r = build_trace_health_result(_trace(segments=segs, time_min=0, time_max=1000))
        chk = _by_id(r, CHECK_LONG_GAP)
        self.assertEqual(chk["severity"], "info")
        self.assertEqual(chk["affected_range"], {"start": 10, "end": 900})
        # info-only checks do not push status past pass
        self.assertEqual(r["status"], STATUS_PASS)

    def test_metric_prerequisites_lists_missing_event_types(self):
        r = build_trace_health_result(_trace(
            segments=[_seg(0, 10, "Core_0")],
            tick_sti_times=[],
            sti_channels=[],
            interval_ids=[],
            has_sync_object_instrumentation=False,
            has_priority_instrumentation=False,
        ))
        chk = _by_id(r, CHECK_METRIC_PREREQUISITES)
        self.assertEqual(chk["severity"], "info")
        self.assertIn("no TICK events", chk["summary"])
        self.assertIn("Trace Health (TICK)", chk["metric_limitations"])

    def test_scope_window_filters_segments(self):
        segs = [_seg(0, 100, "Core_0"), _seg(50, 150, "Core_0")]
        # full trace: overlap present
        self.assertIn(
            CHECK_CORE_INTERVAL_OVERLAP,
            _ids(build_trace_health_result(_trace(segments=segs))),
        )
        # window that only contains the first slice: no overlap
        self.assertNotIn(
            CHECK_CORE_INTERVAL_OVERLAP,
            _ids(build_trace_health_result(_trace(segments=segs), lo=0, hi=40)),
        )

    def test_deterministic(self):
        t = _trace(
            segments=[_seg(0, 100, "Core_0"), _seg(10, 110, "Core_0")],
            sync_issues=[{"kind": "X", "time_ns": 1}],
            meta={"truncated": "true"},
        )
        a = build_trace_health_result(t)
        b = build_trace_health_result(t)
        self.assertEqual(a, b)

    def test_checks_sorted_severity_first(self):
        r = build_trace_health_result(_trace(
            segments=[_seg(0, 100, "Core_0"), _seg(10, 110, "Core_0"),
                      _seg(20, 120, "Core_0")],
            sync_issues=[{"kind": "X", "time_ns": 1}],
        ))
        ranks = {"error": 2, "warning": 1, "info": 0}
        seq = [ranks[c["severity"]] for c in r["checks"]]
        self.assertEqual(seq, sorted(seq, reverse=True))


class LabelAndSummaryTests(unittest.TestCase):
    def test_status_labels(self):
        self.assertEqual(trace_health_status_label(STATUS_PASS), "Pass")
        self.assertEqual(trace_health_status_label(STATUS_CAUTION), "Caution")
        self.assertEqual(
            trace_health_status_label(STATUS_INSUFFICIENT), "Insufficient data")

    def test_summary_text(self):
        clean = build_trace_health_result(_trace(segments=[_seg(0, 10, "Core_0")]))
        self.assertEqual(trace_health_summary(clean), "Trace health: Pass")
        noisy = build_trace_health_result(_trace(
            segments=[_seg(0, 10, "Core_0")], meta={"truncated": "true"}))
        self.assertIn("Caution", trace_health_summary(noisy))
        self.assertIn("issue(s)", trace_health_summary(noisy))


class HtmlCardTests(unittest.TestCase):
    def test_card_renders_status_checks_and_limitations(self):
        r = build_trace_health_result(_trace(
            segments=[_seg(0, 100, "Core_0"), _seg(10, 110, "Core_0")],
            meta={"truncated": "true"},
        ), format_ns=lambda ns: f"{ns}us")
        html = html_trace_health_card(r, format_ns=lambda ns: f"{ns}us",
                                      scope_title=" (C1–C2)")
        self.assertIn("<h2>Trace Health Check (C1–C2)</h2>", html)
        self.assertIn("Status: Insufficient data", html)
        self.assertIn("Trace Health (TICK)", html)  # disambiguation text
        self.assertIn("Limited metrics", html)
        self.assertIn("<details", html)
        # single top-level <section> so the report TOC wrapper stays valid
        self.assertEqual(html.count("<section"), 1)
        self.assertEqual(html.count("</section>"), 1)

    def test_card_empty_result_is_blank(self):
        self.assertEqual(html_trace_health_card(None), "")

    def test_card_pass_state_has_no_check_rows(self):
        r = build_trace_health_result(_trace(
            segments=[_seg(0, 10, "Core_0"), _seg(10, 20, "Core_1")],
        ))
        self.assertEqual(r["checks"], [])
        html = html_trace_health_card(r)
        self.assertIn("Status: Pass", html)
        self.assertIn("No structural inconsistencies", html)


class FixtureRegressionTests(unittest.TestCase):
    """End-to-end against malformed / truncated .btf fixtures."""

    def _parse(self, name):
        from btf_viewer_pkg._bootstrap import install
        install()
        from btf_viewer_pkg.parser import _parse_btf
        return _parse_btf(str(FIXTURES / name))

    def test_clean_fixture_passes(self):
        r = build_trace_health_result(self._parse("clean.btf"))
        self.assertEqual(r["status"], STATUS_PASS)
        self.assertEqual(r["issue_count"], 0)

    def test_truncated_fixture_flags_capture_truncation(self):
        r = build_trace_health_result(self._parse("truncated.btf"))
        self.assertEqual(r["status"], STATUS_CAUTION)
        self.assertIn(CHECK_CAPTURE_TRUNCATION, _ids(r))

    def test_bad_timestamp_fixture_flags_skips(self):
        r = build_trace_health_result(self._parse("bad-timestamps.btf"))
        self.assertIn(CHECK_TIMESTAMP_SKIPS, _ids(r))

    def test_empty_fixture_is_insufficient(self):
        r = build_trace_health_result(self._parse("empty.btf"))
        self.assertEqual(r["status"], STATUS_INSUFFICIENT)
        self.assertEqual(_ids(r), {CHECK_EMPTY_TRACE})

    def test_same_fixture_is_deterministic_across_parses(self):
        self.assertEqual(
            build_trace_health_result(self._parse("truncated.btf")),
            build_trace_health_result(self._parse("truncated.btf")),
        )


class DesktopWebParityTests(unittest.TestCase):
    """The desktop module and web/src/utils/traceHealth.js must stay in step."""

    def test_check_ids_and_public_api_match(self):
        py = (BTF_ROOT / "btf_viewer_pkg" / "trace_health.py").read_text("utf-8")
        js = (BTF_ROOT / "web" / "src" / "utils" / "traceHealth.js").read_text("utf-8")
        for cid in (
            "empty_trace", "timestamp_units", "timestamp_skips",
            "core_interval_overlap", "unknown_core", "missing_task_identity",
            "unmatched_intervals", "sync_pairing_issues", "capture_truncation",
            "long_data_gap", "metric_prerequisites",
        ):
            self.assertIn(f'"{cid}"', py, cid)
            self.assertIn(f"'{cid}'", js, cid)
        for py_name, js_name in (
            ("def build_trace_health_result", "export function buildTraceHealthResult"),
            ("def trace_health_status_label", "export function traceHealthStatusLabel"),
            ("def trace_health_summary", "export function traceHealthSummary"),
        ):
            self.assertIn(py_name, py, py_name)
            self.assertIn(js_name, js, js_name)
        # Shared tuning constants must carry the same values.
        for token in ("0.20", "0.02"):
            self.assertIn(token, py)
            self.assertIn(token, js)


if __name__ == "__main__":
    unittest.main()
