"""Structured evidence cards + provenance.

Parity with web/tests/evidenceCards.test.js.
"""

from __future__ import annotations

import unittest

from btf_viewer_pkg.investigation_notebook import (
    EV_AUTHOR_AI,
    EV_AUTHOR_BTFVIEWER,
    EV_AUTHOR_USER,
    EV_KIND_MEASURED,
    EV_SOURCE_AI,
    EV_SOURCE_STATISTICS,
    EV_SOURCE_USER,
    EVIDENCE_PROTECTED_FIELDS,
    add_evidence,
    apply_evidence_edit,
    detect_broken_references,
    dump_investigation,
    evidence_nav_targets,
    evidence_scope_restore_plan,
    guard_evidence_changes,
    investigation_sections,
    link_bookmarks,
    load_investigation,
    new_investigation,
    normalize_evidence_card,
    update_evidence_explanation,
)


def _measured_inv():
    inv = new_investigation(title="Q", trace_identity={"hash": "abc", "file": "run.btf"})
    inv = add_evidence(
        inv, title="120 migrations", role="supporting",
        source=EV_SOURCE_STATISTICS, kind=EV_KIND_MEASURED, author=EV_AUTHOR_BTFVIEWER,
        value=120, unit="migrations", task="CS[28]",
        refs=[{"kind": "metric", "metric": "migrations"},
              {"kind": "range", "range": {"start": 100, "end": 900}}],
        bookmark_id="e1", created_at="2026-09-08T00:00:00",
    )
    return inv


class ProvenanceRuleTests(unittest.TestCase):
    def test_ai_authored_card_is_never_measured(self) -> None:
        card = normalize_evidence_card(
            {"source": EV_SOURCE_AI, "kind": "measured", "author": "user"},
            refs=[{"kind": "metric", "metric": "x"}],
        )
        self.assertEqual(card["author"], EV_AUTHOR_AI)
        self.assertNotEqual(card["kind"], EV_KIND_MEASURED)

    def test_measured_needs_a_measured_ref(self) -> None:
        # No finding/metric/range ref → cannot be measured even if asked.
        card = normalize_evidence_card(
            {"source": EV_SOURCE_STATISTICS, "kind": "measured", "author": "user"},
            refs=[{"kind": "entity", "entity": "CS[28]"}],
        )
        self.assertNotEqual(card["kind"], EV_KIND_MEASURED)

    def test_user_note_has_no_kind(self) -> None:
        card = normalize_evidence_card(
            {"source": EV_SOURCE_USER, "author": "user"}, refs=[],
        )
        self.assertEqual(card["kind"], "")
        self.assertEqual(card["source"], EV_SOURCE_USER)

    def test_measured_card_keeps_its_source_data(self) -> None:
        secs = {s["id"]: s for s in investigation_sections(_measured_inv())}
        card = secs["evidence"]["items"][0]["card"]
        self.assertEqual(card["kind"], EV_KIND_MEASURED)
        self.assertEqual(card["value"], 120)
        self.assertEqual(card["unit"], "migrations")
        self.assertEqual(card["task"], "CS[28]")
        self.assertEqual(card["scope"], None)  # scope not supplied here


class ProtectedFieldTests(unittest.TestCase):
    def test_guard_rejects_protected_fields_on_measured_card(self) -> None:
        card = {"kind": EV_KIND_MEASURED, "value": 120, "unit": "migrations"}
        allowed, rejected = guard_evidence_changes(
            card, {"value": 999, "unit": "x", "hypothesis_id": "h1", "note": "t"},
        )
        self.assertEqual(sorted(rejected), ["unit", "value"])
        self.assertEqual(set(allowed), {"hypothesis_id", "note"})

    def test_guard_allows_edits_on_a_user_note(self) -> None:
        allowed, rejected = guard_evidence_changes(
            {"kind": ""}, {"value": 5, "unit": "ms"},
        )
        self.assertEqual(rejected, [])
        self.assertEqual(allowed, {"value": 5, "unit": "ms"})

    def test_apply_edit_keeps_measured_values_exactly(self) -> None:
        inv, rejected = apply_evidence_edit(
            _measured_inv(), "e1",
            {"value": 0, "unit": "bogus", "note": "my read of it"},
        )
        b = next(x for x in inv["bookmarks"] if x["id"] == "e1")
        self.assertEqual(b["evidence"]["value"], 120)
        self.assertEqual(b["evidence"]["unit"], "migrations")
        self.assertEqual(b["note"], "my read of it")
        self.assertEqual(sorted(rejected), ["unit", "value"])

    def test_update_explanation_touches_only_note(self) -> None:
        inv = update_evidence_explanation(_measured_inv(), "e1", "explanation")
        b = next(x for x in inv["bookmarks"] if x["id"] == "e1")
        self.assertEqual(b["note"], "explanation")
        self.assertEqual(b["evidence"]["value"], 120)

    def test_cannot_promote_a_note_to_measured(self) -> None:
        allowed, rejected = guard_evidence_changes(
            {"kind": ""}, {"kind": "measured"},
        )
        self.assertIn("kind", rejected)
        self.assertEqual(allowed, {})


class StaleAndNavTests(unittest.TestCase):
    def test_stale_evidence_stays_visible(self) -> None:
        inv = _measured_inv()
        broken = detect_broken_references(
            inv, current_identity={"hash": "DIFFERENT"},
        )
        secs = {s["id"]: s for s in investigation_sections(inv, broken=broken)}
        items = secs["evidence"]["items"]
        self.assertEqual(len(items), 1)               # not deleted
        self.assertTrue(items[0]["stale"])            # flagged

    def test_nav_targets_resolve_from_refs(self) -> None:
        b = {"refs": [
            {"kind": "metric", "metric": "migrations"},
            {"kind": "range", "range": {"start": 10, "end": 20}},
            {"kind": "evidence", "time": 1500},
        ]}
        nav = evidence_nav_targets(b)
        self.assertEqual(nav["stats_metric"], "migrations")
        self.assertEqual(nav["range"], [10, 20])
        self.assertEqual(nav["jump"], 1500)

    def test_measured_fields_survive_export_reload(self) -> None:
        once = dump_investigation(_measured_inv())
        twice = dump_investigation(load_investigation(once))
        self.assertEqual(once, twice)
        card = load_investigation(once)["bookmarks"][0]["evidence"]
        self.assertEqual(card["value"], 120)
        self.assertEqual(card["kind"], EV_KIND_MEASURED)


class ScopeRestorePlanTests(unittest.TestCase):
    """§P1 — separate, previewable Restore-evidence-scope action."""

    def _card(self, start, end):
        return add_evidence(
            new_investigation(), title="e", role="supporting",
            source=EV_SOURCE_STATISTICS, kind="derived",
            scope={"start": start, "end": end},
        )["bookmarks"][0]["evidence"]

    def test_none_without_a_stored_scope(self) -> None:
        self.assertIsNone(evidence_scope_restore_plan({"source": "x"}))
        self.assertIsNone(evidence_scope_restore_plan(None))

    def test_none_when_scope_already_matches_current(self) -> None:
        c = self._card(100, 900)
        self.assertIsNone(evidence_scope_restore_plan(
            c, current_scope={"start": 100, "end": 900}))

    def test_plan_lists_the_changes_for_the_preview(self) -> None:
        c = self._card(100, 900)
        plan = evidence_scope_restore_plan(
            c, current_scope={"start": 0, "end": 50}, fmt=lambda v: f"{v}us")
        self.assertEqual((plan["start"], plan["end"]), (100, 900))
        self.assertIn("100us", plan["summary"])
        self.assertEqual(len(plan["changes"]), 3)
        self.assertTrue(plan["changes"][0].startswith("Place C1–C2"))
        self.assertIn("Limit Statistics", plan["changes"][2])


class LegacyMigrationTests(unittest.TestCase):
    def test_v1_evidence_bookmarks_gain_a_provenance_card(self) -> None:
        legacy = {
            "schema": "btf-viewer-investigation/1",
            "trace_identity": {"hash": "h1"},
            "bookmarks": [
                {"id": "o", "type": "observation", "title": "bare note"},
                {"id": "s", "type": "supporting", "title": "measured",
                 "refs": [{"kind": "finding", "rule_id": "thrash"}]},
                {"id": "h", "type": "hypothesis", "title": "a guess"},
            ],
        }
        loaded = load_investigation(legacy)
        by_id = {b["id"]: b for b in loaded["bookmarks"]}
        self.assertEqual(by_id["o"]["evidence"]["source"], EV_SOURCE_USER)
        self.assertEqual(by_id["o"]["evidence"]["kind"], "")
        self.assertEqual(by_id["s"]["evidence"]["kind"], EV_KIND_MEASURED)
        self.assertEqual(by_id["s"]["evidence"]["author"], EV_AUTHOR_USER)
        self.assertNotIn("evidence", by_id["h"])  # hypotheses are not evidence

    def test_protected_field_list_is_the_source_data(self) -> None:
        for f in ("trace_id", "scope", "task", "core", "value", "unit",
                  "kind", "source", "author"):
            self.assertIn(f, EVIDENCE_PROTECTED_FIELDS)


if __name__ == "__main__":
    unittest.main()
