"""Per-metric availability, percentile disclosure, two-endpoint jumps, metric definitions."""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import unittest

from btf_viewer_pkg import _bootstrap

_bootstrap.install()

from btf_viewer_pkg.ai_evidence_package import (  # noqa: E402
    build_evidence_package,
    format_evidence_package_preview,
)
from btf_viewer_pkg.parser import (  # noqa: E402
    METRIC_DEFINITIONS,
    PERCENTILE_METHOD_NOTE,
    _affinity_change_note,
    _dispatch_latency_by_mk,
    _dispatch_source_note,
    _interval_exec_note,
    _metric_definitions_for,
    _migration_gap_baseline_note,
    _parse_btf,
    _priority_holder_note,
    _suspended_duration_note,
    _percentile_sample_note,
    _plot_point_endpoint_notes,
    _plot_point_endpoints,
)
from btf_viewer_pkg.stats_html import (  # noqa: E402
    html_metric_definitions_card,
    html_trace_health_card,
)
from btf_viewer_pkg.trace_health import (  # noqa: E402
    build_trace_health_result,
    metric_availability_lines,
)

from tests.test_latency_metrics import _TEXT, _parse  # noqa: E402


class MetricReportingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.trace = _parse(_TEXT)
        cls.health = build_trace_health_result(cls.trace, 0, 600)

    def test_availability_states_and_reasons(self) -> None:
        by = {a["metric"]: a for a in self.health["metric_availability"]}
        self.assertEqual(by["Dispatch / Scheduling Latency"]["state"], "available")
        self.assertEqual(by["Mutex / Semaphore / Queue"]["state"], "unavailable")
        self.assertIn("no mutex", by["Mutex / Semaphore / Queue"]["reason"])
        self.assertEqual(by["Trace Health (TICK)"]["state"], "unavailable")
        lines = metric_availability_lines(self.health)
        self.assertEqual(len(lines), 2)
        self.assertTrue(all(" — " in ln for ln in lines))

    def test_health_card_lists_availability(self) -> None:
        html = html_trace_health_card(self.health)
        self.assertIn("Metric availability", html)
        self.assertIn("no TICK events", html)

    def test_percentile_sample_note(self) -> None:
        self.assertEqual(_percentile_sample_note([100, 500]), "")
        note = _percentile_sample_note([5, 50, 200])
        self.assertIn("fewer than 20 samples", note)
        self.assertIn("20–99 samples", note)
        self.assertTrue(note.endswith(PERCENTILE_METHOD_NOTE))

    def test_plot_point_endpoints(self) -> None:
        self.assertEqual(_plot_point_endpoints({"start_ns": 10, "stop_ns": 20}), (10, 20))
        self.assertIsNone(_plot_point_endpoints({"start_ns": 10}))
        self.assertEqual(_plot_point_endpoint_notes("x"), ("x — start", "x — end"))

    def test_definitions_card_and_evidence(self) -> None:
        card = html_metric_definitions_card()
        for _key, term, _text, _kws in METRIC_DEFINITIONS:
            self.assertIn(term, card)
        keys = [d["key"] for d in _metric_definitions_for(["Dispatch p95"])]
        self.assertEqual(keys, ["dispatch", "percentile"])
        pkg = build_evidence_package(
            question="why late?", health=self.health,
            statistics=[{"name": "Dispatch p95", "value": 10, "unit": "ns", "sample_count": 3}])
        self.assertEqual([d["key"] for d in pkg["definitions"]], ["dispatch", "percentile"])
        self.assertEqual(
            {a["metric"] for a in pkg["trace_health"]["availability"]},
            {"Mutex / Semaphore / Queue", "Trace Health (TICK)"})
        preview = format_evidence_package_preview(pkg)
        self.assertIn("Definitions (2):", preview)
        self.assertIn("no TICK events", preview)

    @unittest.skipUnless(shutil.which("node"), "node not installed")
    def test_definitions_match_web(self) -> None:
        web = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "web")
        script = ("import { METRIC_DEFINITIONS } from './src/utils/latencyMetrics.js';"
                  "console.log(JSON.stringify(METRIC_DEFINITIONS))")
        web_defs = json.loads(subprocess.check_output(
            ["node", "--input-type=module", "-e", script], cwd=web, text=True))
        self.assertEqual(web_defs, [[k, t, d, list(kw)] for k, t, d, kw in METRIC_DEFINITIONS])

    @unittest.skipUnless(shutil.which("node"), "node not installed")
    def test_captions_match_web_on_example_trace(self) -> None:
        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        trace_path = os.path.join(os.path.dirname(root), "tracedata", "example-4cores.btf.gz")
        if not os.path.exists(trace_path):
            self.skipTest("example-4cores.btf.gz not available")
        tr = _parse_btf(trace_path)
        by = _dispatch_latency_by_mk(tr)
        desktop = {
            "dispatch": _dispatch_source_note(tr, by),
            "migration": _migration_gap_baseline_note(tr),
            "priority": _priority_holder_note(tr),
            "affinity": _affinity_change_note(tr),
            "suspended": _suspended_duration_note(tr),
            "interval": _interval_exec_note(tr),
            "availability": metric_availability_lines(build_trace_health_result(tr, None, None)),
        }
        script = """
import { readFileSync } from 'node:fs'
import { parseBtf } from './src/parser/btfParser.js'
import { decompressBtfBytes } from './src/utils/btfLoad.js'
import { collectDispatchLatencyByMk } from './src/utils/schedulerSmpMetrics.js'
import { buildTraceHealthResult, metricAvailabilityLines } from './src/utils/traceHealth.js'
import * as L from './src/utils/latencyMetrics.js'
const p = process.argv[1]
const tr = await parseBtf(decompressBtfBytes(new Uint8Array(readFileSync(p)), p))
console.log(JSON.stringify({
  dispatch: L.dispatchSourceNote(tr, collectDispatchLatencyByMk(tr, null, null)),
  migration: L.migrationGapBaselineNote(tr),
  priority: L.priorityHolderNote(tr),
  affinity: L.affinityChangeNote(tr),
  suspended: L.suspendedDurationNote(tr),
  interval: L.intervalExecNote(tr),
  availability: metricAvailabilityLines(buildTraceHealthResult(tr, null, null)),
}))
"""
        web = json.loads(subprocess.check_output(
            ["node", "--input-type=module", "-e", script, trace_path],
            cwd=os.path.join(root, "web"), text=True))
        self.assertEqual(web, desktop)


if __name__ == "__main__":
    unittest.main()
