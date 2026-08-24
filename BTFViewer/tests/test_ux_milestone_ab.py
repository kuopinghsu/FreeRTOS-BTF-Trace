"""UX Milestones A+B lockstep tests."""
from __future__ import annotations

import unittest

from btf_viewer_pkg.analysis_context import (
    build_analysis_context,
    format_analysis_context_strip,
    is_context_stale,
)
from btf_viewer_pkg.cursor_scope import format_use_as_scope_prompt, should_offer_use_as_scope
from btf_viewer_pkg.evidence_history import SHOW_ON_TIMELINE_LABEL, push_evidence_entry
from btf_viewer_pkg.evidence_strength import evidence_strength_badge
from btf_viewer_pkg.findings_triage import (
    enrich_finding_card,
    sort_findings_triage,
    filter_findings_triage,
    finding_filter_facets,
    group_findings_by_incident,
    format_investigate_preview,
    apply_triage_action,
    finding_queue_status,
    filter_by_queue,
    queue_counts,
    format_triage_audit_text,
    SORT_TITLE,
    SORT_CATEGORY,
    QUEUE_OPEN,
    QUEUE_DONE,
    QUEUE_CASE,
    QUEUE_DISMISSED,
)
from btf_viewer_pkg.ai_case import add_finding_to_case, empty_investigation_case
from btf_viewer_pkg.guided_investigation import GUIDED_REVIEW_STEPS
from btf_viewer_pkg.stats_symptom_landing import available_symptom_cards
from btf_viewer_pkg.trace_quality import trace_quality_report


class UxMilestoneAbTests(unittest.TestCase):
    def test_analysis_context_cursors_without_limit(self) -> None:
        ctx = build_analysis_context(
            trace_name="demo.btf",
            scope_label="Full Trace",
            cursor_count=2,
            limit_to_cursors=False,
        )
        strip = format_analysis_context_strip(ctx)
        self.assertIn("Not limited to cursors", strip)
        compact = format_analysis_context_strip(ctx, compact=True)
        self.assertEqual(compact, "Not limited to cursors")
        self.assertNotIn("Samples:", compact)
        self.assertNotIn("Scope:", compact)

    def test_stale_context_detection(self) -> None:
        a = build_analysis_context(scope_label="Full Trace", filter_labels=[])
        b = build_analysis_context(scope_label="C1–C2", filter_labels=["Task: foo"])
        self.assertFalse(is_context_stale(a, a))
        self.assertTrue(is_context_stale(a, b))

    def test_cursor_use_as_scope_prompt(self) -> None:
        self.assertTrue(should_offer_use_as_scope([1, 2], limit_to_cursors=False))
        self.assertIn("C1–C2", format_use_as_scope_prompt([1, 2]))

    def test_findings_triage_card(self) -> None:
        card = enrich_finding_card({
            "title": "Migration thrash",
            "text": "Task bounces",
            "evidence": [{"label": "migrations: burst", "time": 100}],
        })
        self.assertEqual(card["observation"], "Migration thrash")
        self.assertIn("jump:100", card["evidence_text"])

    def test_symptom_landing_disables_sync_without_sti(self) -> None:
        cards = available_symptom_cards(has_sti=False, single_core=False)
        sync = next(c for c in cards if c["id"] == "sync")
        self.assertTrue(sync.get("disabled"))

    def test_trace_quality_report_groups(self) -> None:
        class _T:
            meta = {"traceQuality": {"ringOverflow": True}}
        rep = trace_quality_report(_T())
        self.assertFalse(rep["ok"])
        self.assertTrue(rep["groups"])

    def test_evidence_strength_estimated(self) -> None:
        badge = evidence_strength_badge("estimated")
        self.assertIn("Estimated", badge["label"])

    def test_guided_review_steps(self) -> None:
        self.assertGreaterEqual(len(GUIDED_REVIEW_STEPS), 6)

    def test_evidence_history_roundtrip(self) -> None:
        hist = push_evidence_entry(None, {"time": 42, "task": "T"})
        self.assertEqual(hist["index"], 0)

    def test_symptom_section_map(self) -> None:
        from btf_viewer_pkg.stats_symptom_landing import symptom_card, symptom_section_id
        card = symptom_card("late")
        self.assertIsNotNone(card)
        self.assertEqual(symptom_section_id(card), "response")

    def test_show_on_timeline_label(self) -> None:
        self.assertEqual(SHOW_ON_TIMELINE_LABEL, "Show on timeline")

    def test_findings_sorted_by_severity(self) -> None:
        items = sort_findings_triage([
            {"severity": "info", "title": "a"},
            {"severity": "error", "title": "b"},
        ])
        self.assertEqual(items[0]["severity"], "error")

    def test_findings_sort_title_and_category(self) -> None:
        by_title = sort_findings_triage([
            {"severity": "error", "title": "Zebra"},
            {"severity": "info", "title": "Alpha"},
        ], sort_by=SORT_TITLE)
        self.assertEqual(by_title[0]["title"], "Alpha")
        by_cat = sort_findings_triage([
            {"severity": "info", "title": "Load imbalance"},
            {"severity": "error", "title": "Migration thrash"},
        ], sort_by=SORT_CATEGORY)
        self.assertEqual(by_cat[0]["category"], "load")
        self.assertEqual(by_cat[1]["category"], "migration")

    def test_findings_category_task_core_filters(self) -> None:
        items = [
            {"id": "1", "severity": "error", "title": "Migration thrash",
             "task": "ControlTask", "text": "Core_0 bounce"},
            {"id": "2", "severity": "warning", "title": "Long blocking",
             "task": "Idle", "text": "mutex wait"},
        ]
        mig = filter_findings_triage(items, category="migration")
        self.assertEqual([f["id"] for f in mig], ["1"])
        ctl = filter_findings_triage(items, task="controltask")
        self.assertEqual([f["id"] for f in ctl], ["1"])
        core = filter_findings_triage(items, core="core_0")
        self.assertEqual([f["id"] for f in core], ["1"])
        facets = finding_filter_facets(items)
        self.assertIn("migration", facets["categories"])
        self.assertIn("ControlTask", facets["tasks"])

    def test_group_findings_by_incident(self) -> None:
        findings = [
            {"id": "a", "title": "Late A", "severity": "error"},
            {"id": "b", "title": "Late B", "severity": "warning"},
            {"id": "c", "title": "Other", "severity": "info"},
        ]
        clusters = [{
            "id": "INC-1", "count": 2, "root_suspect": "deadline",
            "finding_ids": ["a", "b"], "findings": ["Late A", "Late B"],
        }]
        rows = group_findings_by_incident(findings, clusters, group=True)
        kinds = [r["kind"] for r in rows]
        self.assertEqual(kinds.count("header"), 1)
        self.assertGreaterEqual(kinds.count("finding"), 3)
        flat = group_findings_by_incident(findings, clusters, group=False)
        self.assertTrue(all(r["kind"] == "finding" for r in flat))

    def test_investigate_preview_text(self) -> None:
        text = format_investigate_preview(
            {"title": "Late", "id": "x"},
            scope={"lo": 10, "hi": 20, "reason": "evidence window"},
            section_id="response",
            section_label="Response Time",
            current_limit=True,
            current_lo=1,
            current_hi=5,
        )
        self.assertIn("Investigate will:", text)
        self.assertIn("Response Time", text)
        self.assertIn("10–20", text)
        self.assertIn("Replaces current Scope 1–5", text)
        self.assertIn("Undo", text)

    def test_findings_queue_and_case(self) -> None:
        findings = [
            {"id": "a", "title": "A", "severity": "error"},
            {"id": "b", "title": "B", "severity": "warning"},
        ]
        st = apply_triage_action(None, "a", "done")
        self.assertEqual(finding_queue_status("a", st), QUEUE_DONE)
        self.assertEqual(finding_queue_status("b", st), QUEUE_OPEN)
        st = apply_triage_action(st, "a", "case")
        self.assertEqual(finding_queue_status("a", st), QUEUE_CASE)
        st = apply_triage_action(st, "b", "dismiss", reason="noise")
        self.assertEqual(finding_queue_status("b", st), QUEUE_DISMISSED)
        counts = queue_counts(findings, st)
        self.assertEqual(counts[QUEUE_CASE], 1)
        self.assertEqual(counts[QUEUE_DISMISSED], 1)
        self.assertEqual(counts[QUEUE_OPEN], 0)
        case_items = filter_by_queue(findings, st, queue=QUEUE_CASE)
        self.assertEqual([f["id"] for f in case_items], ["a"])
        audit = format_triage_audit_text(findings, st)
        self.assertIn("Dismissed:", audit)
        self.assertIn("noise", audit)
        cse = add_finding_to_case(empty_investigation_case(), findings[0])
        cse = add_finding_to_case(cse, findings[0])  # dedupe
        self.assertEqual(len(cse["suspected_findings"]), 1)
        self.assertEqual(cse["goal"], "A")


if __name__ == "__main__":
    unittest.main()
