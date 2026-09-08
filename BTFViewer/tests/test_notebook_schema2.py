"""Investigation Notebook schema/2: versioned migration, durable status, and the
six-section projection (BTFVIEWER_DESIGN_CONSISTENCY_TODO §7).

Parity with web/tests/notebookSchema2.test.js.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

BTF_ROOT = Path(__file__).resolve().parents[1]
if str(BTF_ROOT) not in sys.path:
    sys.path.insert(0, str(BTF_ROOT))

from btf_viewer_pkg.investigation_notebook import (  # noqa: E402
    INVESTIGATION_SCHEMA,
    NB_SECTION_ORDER,
    NB_STATUS_CLOSED,
    NB_STATUS_NEEDS_EVIDENCE,
    NB_STATUS_OPEN,
    NB_STATUS_READY,
    NOTEBOOK_STATUSES,
    add_bookmark,
    add_unresolved_question,
    derive_status,
    dump_investigation,
    investigation_header,
    investigation_sections,
    link_bookmarks,
    load_investigation,
    new_investigation,
    set_conclusion,
    set_status,
)


def _legacy_v1(**extra):
    inv = {
        "schema": "btf-viewer-investigation/1",
        "title": "Why does CS[28] miss its deadline?",
        "trace_identity": {"file": "run.btf", "time_scale": "ns"},
        "analysis_range": {"start": 100, "end": 900},
        "bookmarks": [
            {"id": "h1", "type": "hypothesis", "title": "Core thrash", "seq": 1},
            {"id": "s1", "type": "supporting", "title": "120 migrations",
             "seq": 2, "refs": [{"kind": "metric", "metric": "migrations"}]},
            {"id": "o1", "type": "observation", "title": "note", "seq": 3},
            {"id": "v1", "type": "verification", "title": "pin CS[28]", "seq": 4},
        ],
        "links": [{"from": "s1", "to": "h1", "relation": "supports"}],
        "conclusion": "",
        "unresolved_questions": ["Is the affinity mask correct?"],
    }
    inv.update(extra)
    return inv


class SchemaMigrationTests(unittest.TestCase):
    def test_schema_is_v2(self) -> None:
        self.assertEqual(INVESTIGATION_SCHEMA, "btf-viewer-investigation/2")
        self.assertEqual(new_investigation()["schema"], INVESTIGATION_SCHEMA)

    def test_v1_payload_upgrades_without_losing_anything(self) -> None:
        loaded = load_investigation(_legacy_v1())
        self.assertEqual(loaded["schema"], INVESTIGATION_SCHEMA)
        self.assertEqual([b["id"] for b in loaded["bookmarks"]],
                         ["h1", "s1", "o1", "v1"])
        self.assertEqual(loaded["links"],
                         [{"from": "s1", "to": "h1", "relation": "supports"}])
        self.assertEqual(loaded["unresolved_questions"],
                         ["Is the affinity mask correct?"])
        self.assertIn(loaded["status"], NOTEBOOK_STATUSES)

    def test_stored_status_is_preserved_over_derivation(self) -> None:
        loaded = load_investigation(_legacy_v1(status="closed"))
        self.assertEqual(loaded["status"], NB_STATUS_CLOSED)

    def test_round_trip_stays_stable(self) -> None:
        once = dump_investigation(load_investigation(_legacy_v1()))
        twice = dump_investigation(load_investigation(once))
        self.assertEqual(once, twice)

    def test_transient_workflow_stage_is_not_promoted(self) -> None:
        loaded = load_investigation(_legacy_v1(workflow_stage="triage"))
        self.assertEqual(loaded["workflow_stage"], "triage")  # preserved as-is
        self.assertNotEqual(loaded["status"], "triage")
        self.assertIn(loaded["status"], NOTEBOOK_STATUSES)


class DeriveStatusTests(unittest.TestCase):
    def test_blank_is_open(self) -> None:
        self.assertEqual(derive_status(new_investigation()), NB_STATUS_OPEN)

    def test_hypothesis_without_evidence_needs_evidence(self) -> None:
        inv = add_bookmark(new_investigation(), type="hypothesis", title="h")
        self.assertEqual(derive_status(inv), NB_STATUS_NEEDS_EVIDENCE)

    def test_open_questions_need_evidence(self) -> None:
        inv = add_unresolved_question(new_investigation(), "why?")
        self.assertEqual(derive_status(inv), NB_STATUS_NEEDS_EVIDENCE)

    def test_conclusion_is_ready_not_closed(self) -> None:
        inv = set_conclusion(new_investigation(), "Confirmed: core thrash")
        self.assertEqual(derive_status(inv), NB_STATUS_READY)

    def test_derive_never_returns_closed(self) -> None:
        inv = set_conclusion(new_investigation(), "done")
        inv = add_unresolved_question(inv, "q")
        self.assertNotEqual(derive_status(inv), NB_STATUS_CLOSED)

    def test_set_status_validates(self) -> None:
        inv = set_status(new_investigation(), "bogus")
        self.assertEqual(inv["status"], NB_STATUS_OPEN)
        inv = set_status(inv, "closed", updated_at="2026-09-08T00:00:00")
        self.assertEqual(inv["status"], NB_STATUS_CLOSED)
        self.assertEqual(inv["updated_at"], "2026-09-08T00:00:00")


class SectionProjectionTests(unittest.TestCase):
    def test_six_sections_in_order(self) -> None:
        secs = investigation_sections(_legacy_v1())
        self.assertEqual([s["id"] for s in secs], list(NB_SECTION_ORDER))
        self.assertEqual(
            [s["title"] for s in secs],
            ["Question", "Scope", "Hypotheses", "Evidence", "Open checks",
             "Conclusion"],
        )

    def test_bookmarks_land_in_the_right_sections(self) -> None:
        secs = {s["id"]: s for s in investigation_sections(_legacy_v1())}
        self.assertEqual(secs["question"]["items"][0]["text"],
                         "Why does CS[28] miss its deadline?")
        self.assertEqual([i.get("bookmark_id") for i in secs["hypotheses"]["items"]],
                         ["h1"])
        self.assertEqual(secs["hypotheses"]["items"][0]["status"], "supported")
        ev_ids = [i["bookmark_id"] for i in secs["evidence"]["items"]]
        self.assertEqual(sorted(ev_ids), ["o1", "s1"])
        # s1 references a measured metric → Measured; o1 is a bare note.
        self.assertEqual(
            {i["bookmark_id"]: i["kind"] for i in secs["evidence"]["items"]},
            {"s1": "measured", "o1": ""},
        )
        cards = {i["bookmark_id"]: i["card"] for i in secs["evidence"]["items"]}
        self.assertEqual(cards["s1"]["source"], "Statistics")
        self.assertEqual(cards["s1"]["author"], "user")   # legacy → user-authored
        self.assertEqual(cards["o1"]["source"], "User note")
        open_texts = [i["text"] for i in secs["open_checks"]["items"]]
        self.assertIn("Is the affinity mask correct?", open_texts)
        self.assertIn("pin CS[28]", open_texts)

    def test_contradicting_link_marks_hypothesis(self) -> None:
        inv = new_investigation()
        inv = add_bookmark(inv, type="hypothesis", title="h", bookmark_id="h")
        inv = add_bookmark(inv, type="contradicting", title="counter", bookmark_id="c")
        inv = link_bookmarks(inv, "c", "h", "contradicts")
        secs = {s["id"]: s for s in investigation_sections(inv)}
        self.assertEqual(secs["hypotheses"]["items"][0]["status"], "contradicted")

    def test_projection_does_not_require_ai(self) -> None:
        # No AI import path — investigation_sections is a pure function.
        secs = investigation_sections(new_investigation(title="Q"))
        self.assertEqual(secs[0]["items"], [{"text": "Q"}])


class HeaderTests(unittest.TestCase):
    def test_header_counts(self) -> None:
        hdr = investigation_header(_legacy_v1())
        self.assertEqual(hdr["trace"], "run.btf")
        self.assertEqual(hdr["scope"], "100–900")
        self.assertEqual(hdr["hypothesis_count"], 1)
        self.assertEqual(hdr["evidence_count"], 2)
        self.assertEqual(hdr["open_check_count"], 2)
        self.assertEqual(hdr["stale_ref_count"], 0)
        self.assertIn(hdr["status"], NOTEBOOK_STATUSES)
        self.assertEqual(hdr["status_label"], "Needs evidence")

    def test_header_takes_broken_ref_result(self) -> None:
        hdr = investigation_header(
            _legacy_v1(), broken={"issues": [{"bookmark_id": "s1"}, {"bookmark_id": "x"}]},
        )
        self.assertEqual(hdr["stale_ref_count"], 2)


if __name__ == "__main__":
    unittest.main()
