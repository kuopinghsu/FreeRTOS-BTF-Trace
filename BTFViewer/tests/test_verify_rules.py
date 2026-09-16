"""Headless ``verify`` rule engine + CLI exit-code contract."""
from __future__ import annotations

import io
import json
import sys
import tempfile
import types
import unittest
from contextlib import redirect_stdout
from pathlib import Path

BTF_ROOT = Path(__file__).resolve().parents[1]
if str(BTF_ROOT) not in sys.path:
    sys.path.insert(0, str(BTF_ROOT))

from btf_viewer_pkg._bootstrap import install  # noqa: E402

install()

from btf_viewer_pkg.cli import _cli_verify_run  # noqa: E402
from btf_viewer_pkg.verify_rules import (  # noqa: E402
    EXIT_FAIL, EXIT_INPUT, EXIT_PASS,
    format_verification_report, parse_rules, run_verification, supported_metrics,
)

_SNAP = {
    "span_ns": 1_000_000_000,
    "load_balance_score": 82.0,
    "load_balance_sigma": 6.0,
    "migrations": 610,
    "migrated_tasks": 43,
    "context_switches": 2897,
    "gap_avg_ns": 14_000,
    "gap_max_ns": 17_000,
    "tick_health": "GOOD",
    "missed_ticks": 0,
}
_HEALTH = {"status": "caution"}


class RuleParsingTests(unittest.TestCase):
    def test_rejects_bad_schema_and_empty(self):
        for bad in ('{"schema_version": 2, "rules": [{"metric": "x", "max": 1}]}',
                    '{"rules": []}', 'not json', '[]',
                    '{"schema_version": 1, "rules": [{"max": 1}]}',
                    '{"schema_version": 1, "rules": [{"metric": "x"}]}'):
            with self.assertRaises(ValueError):
                parse_rules(bad)

    def test_threshold_forms(self):
        r = parse_rules(json.dumps({"schema_version": 1, "rules": [
            {"metric": "load_balance_score", "min": 70},
            {"metric": "gap_max_ns", "maximum_us": 50},
            {"metric": "trace_health", "expect_one_of": ["pass", "caution"]},
            {"metric": "tick_health", "expect": "GOOD"},
        ]}))["rules"]
        self.assertEqual(r[0]["min"], 70.0)
        self.assertEqual(r[1]["max"], 50.0)
        self.assertEqual(r[1]["threshold_unit"], "us")
        self.assertEqual(r[2]["expect"], ["pass", "caution"])
        self.assertEqual(r[3]["expect"], ["GOOD"])

    def test_supported_metrics_lists_derived_and_trace_wide(self):
        m = supported_metrics()
        self.assertIn("trace_health", m)
        self.assertIn("migration_rate_per_s", m)
        self.assertIn("load_balance_score", m)


class RuleEvaluationTests(unittest.TestCase):
    def _run(self, rules, **kw):
        return run_verification(_SNAP, _HEALTH, parse_rules(json.dumps(
            {"schema_version": 1, "rules": rules})), **kw)

    def test_pass_and_error_severity_fail(self):
        res = self._run([
            {"metric": "load_balance_score", "min": 70},          # 82 pass
            {"metric": "migrations", "max": 100, "severity": "error"},  # 610 fail
        ])
        self.assertEqual(res["exit_code"], EXIT_FAIL)
        self.assertEqual(res["failed"], 1)

    def test_warning_only_failure_still_passes_unless_strict(self):
        rules = [{"metric": "migrations", "max": 100, "severity": "warning"}]
        self.assertEqual(self._run(rules)["exit_code"], EXIT_PASS)
        self.assertEqual(self._run(rules, strict=True)["exit_code"], EXIT_FAIL)

    def test_unit_suffix_and_maximum_us(self):
        res = self._run([{"metric": "gap_max_us", "max": 50}])   # 17000ns -> 17us
        self.assertEqual(res["results"][0]["status"], "pass")
        self.assertEqual(res["results"][0]["value"], 17.0)

    def test_unknown_metric_and_missing_data_are_data_errors(self):
        res = self._run([
            {"metric": "no_such_metric", "max": 1},
            {"metric": "load_balance_score", "min": 999},   # a real fail, not error
        ])
        self.assertEqual(res["errored"], 1)
        self.assertEqual(res["exit_code"], EXIT_INPUT)

    def test_trace_health_expect_and_rank(self):
        self.assertEqual(
            self._run([{"metric": "trace_health", "expect_one_of": ["pass"]}])
            ["results"][0]["status"], "fail")           # caution not in [pass]
        self.assertEqual(
            self._run([{"metric": "trace_health", "max": 1}])
            ["results"][0]["status"], "pass")           # caution rank 1 <= 1
        self.assertEqual(
            self._run([{"metric": "trace_health", "max": 0}])
            ["results"][0]["status"], "fail")

    def test_status_metric_string_match(self):
        self.assertEqual(
            self._run([{"metric": "tick_health", "expect": "GOOD"}])
            ["results"][0]["status"], "pass")
        self.assertEqual(
            self._run([{"metric": "tick_health", "expect": "BAD"}])
            ["results"][0]["status"], "fail")

    def test_per_entity_metric_is_a_data_error(self):
        res = self._run([{"metric": "wakeup_latency_p99", "entity": "T1", "maximum_us": 50}])
        self.assertEqual(res["results"][0]["status"], "error")
        self.assertEqual(res["exit_code"], EXIT_INPUT)

    def test_report_text_is_stable(self):
        txt = format_verification_report(
            self._run([{"metric": "load_balance_score", "min": 70}]), title="t")
        self.assertIn("PASS", txt)
        self.assertIn("exit 0", txt)


class CliVerifyExitCodeTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.tmp = Path(self._tmp.name)
        self.trace = BTF_ROOT.parent / "tracedata" / "example-2cores.btf.gz"
        if not self.trace.is_file():
            self.skipTest(f"missing {self.trace}")

    def _rules(self, rules):
        p = self.tmp / "rules.json"
        p.write_text(json.dumps({"schema_version": 1, "rules": rules}), encoding="utf-8")
        return str(p)

    def _args(self, rules_path, **kw):
        base = dict(trace=str(self.trace), rules=rules_path, lo=None, hi=None,
                    strict=False, json=False, list_metrics=False)
        base.update(kw)
        return types.SimpleNamespace(**base)

    def _run(self, args):
        buf = io.StringIO()
        with redirect_stdout(buf):
            code = _cli_verify_run(args)
        return code, buf.getvalue()

    def test_exit_0_when_all_pass(self):
        code, out = self._run(self._args(self._rules([
            {"metric": "load_balance_score", "min": 10},
            {"metric": "trace_health", "expect_one_of": ["pass", "caution"]},
        ])))
        self.assertEqual(code, 0)
        self.assertIn("exit 0", out)

    def test_exit_1_on_error_limit(self):
        code, _ = self._run(self._args(self._rules([
            {"metric": "load_balance_score", "min": 100, "severity": "error"},
        ])))
        self.assertEqual(code, 1)

    def test_exit_2_on_bad_rules(self):
        p = self.tmp / "bad.json"
        p.write_text("{ not json", encoding="utf-8")
        code, _ = self._run(self._args(str(p)))
        self.assertEqual(code, 2)

    def test_exit_2_on_missing_trace(self):
        code, _ = self._run(self._args(
            self._rules([{"metric": "migrations", "max": 1}]),
            trace=str(self.tmp / "nope.btf")))
        self.assertEqual(code, 2)

    def test_list_metrics(self):
        code, out = self._run(self._args("x", list_metrics=True))
        self.assertEqual(code, 0)
        self.assertIn("trace_health", out)

    def test_json_output(self):
        code, out = self._run(self._args(
            self._rules([{"metric": "migrations", "max": 5, "severity": "warning"}]),
            json=True))
        payload = json.loads(out)
        self.assertIn("results", payload)
        self.assertEqual(payload["exit_code"], code)


if __name__ == "__main__":
    unittest.main()
