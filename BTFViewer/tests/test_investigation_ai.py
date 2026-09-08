"""Collaborate-with-AI + AI proposal review (BTFVIEWER_DESIGN_CONSISTENCY_TODO §9, §10).

Parity with web/tests/investigationAi.test.js.
"""

from __future__ import annotations

import unittest

from btf_viewer_pkg.investigation_notebook import (
    add_bookmark,
    add_evidence,
    new_investigation,
)
from btf_viewer_pkg.investigation_ai import (
    NB_AI_ACTIONS,
    NB_AI_DISABLED_REASON,
    OP_CONFIRM,
    OP_OK,
    OP_REJECTED,
    PROPOSAL_SCHEMA,
    apply_proposal,
    collaborate_context,
    collaborate_header,
    nb_ai_action_reason,
    proposal_diff,
    strip_model_secrets,
    validate_proposal,
)


def _inv():
    inv = new_investigation(title="Why deadline miss?", trace_identity={"hash": "abc", "file": "run.btf"})
    inv = add_evidence(
        inv, title="120 migrations", role="supporting", source="Statistics",
        kind="measured", author="btfviewer", value=120, unit="migrations",
        refs=[{"kind": "metric", "metric": "migrations"}], bookmark_id="e1",
    )
    inv = add_bookmark(inv, type="hypothesis", title="core thrash", bookmark_id="h1")
    return inv


class CollaborateEntryPointTests(unittest.TestCase):
    def test_six_focused_actions(self) -> None:
        self.assertEqual(
            [a[0] for a in NB_AI_ACTIONS],
            ["review_investigation", "suggest_next_check", "draft_hypotheses",
             "draft_conclusion", "update_from_findings", "compare_trace"],
        )

    def test_disabled_when_ai_unavailable(self) -> None:
        self.assertEqual(
            nb_ai_action_reason("review_investigation", _inv(), ai_enabled=False),
            NB_AI_DISABLED_REASON,
        )

    def test_compare_needs_a_second_trace(self) -> None:
        self.assertIn(
            "second trace",
            nb_ai_action_reason("compare_trace", _inv(), ai_enabled=True),
        )
        self.assertEqual(
            nb_ai_action_reason("compare_trace", _inv(), ai_enabled=True,
                                has_second_trace=True),
            "",
        )

    def test_draft_conclusion_needs_evidence(self) -> None:
        blank = new_investigation(title="x")
        self.assertIn("evidence",
                      nb_ai_action_reason("draft_conclusion", blank, ai_enabled=True))
        self.assertEqual(
            nb_ai_action_reason("draft_conclusion", _inv(), ai_enabled=True), "")

    def test_context_sends_only_selected_evidence(self) -> None:
        ctx = collaborate_context(_inv(), action="draft_conclusion",
                                  selected_evidence_ids=["e1"])
        self.assertEqual(ctx["action"], "draft_conclusion")
        self.assertEqual(len(ctx["selected_evidence"]), 1)
        self.assertEqual(ctx["selected_evidence"][0]["bookmark_id"], "e1")
        self.assertIn("sections", ctx["investigation"])
        self.assertNotIn("bookmarks", ctx["investigation"])  # projection, not raw

    def test_header_reports_stale(self) -> None:
        hdr = collaborate_header(
            _inv(), broken={"issues": [{"bookmark_id": "e1"}]},
        )
        self.assertIn("no longer resolve", hdr["stale_warning"])


class ProposalValidationTests(unittest.TestCase):
    def test_ai_add_measured_is_downgraded_not_measured(self) -> None:
        v = validate_proposal(_inv(), {"operations": [
            {"op": "add", "role": "supporting", "title": "AI: mask wrong",
             "kind": "measured", "author": "ai"},
        ]})
        op = v["operations"][0]
        self.assertEqual(op["status"], OP_OK)
        self.assertNotEqual(op["card"]["kind"], "measured")

    def test_update_measured_field_is_rejected(self) -> None:
        v = validate_proposal(_inv(), {"operations": [
            {"op": "update", "bookmark_id": "e1", "changes": {"value": 999, "unit": "x"}},
        ]})
        op = v["operations"][0]
        self.assertEqual(op["status"], OP_REJECTED)
        self.assertIn("measured data not changed", op["reason"])

    def test_close_and_remove_need_confirmation(self) -> None:
        v = validate_proposal(_inv(), {"operations": [
            {"op": "change_status", "status": "closed"},
            {"op": "remove", "bookmark_id": "e1"},
        ]})
        self.assertEqual([o["status"] for o in v["operations"]],
                         [OP_CONFIRM, OP_CONFIRM])

    def test_other_trace_without_compare_is_rejected(self) -> None:
        v = validate_proposal(_inv(), {"operations": [
            {"op": "add", "role": "supporting", "title": "from other run",
             "trace_id": "OTHER"},
        ]})
        self.assertEqual(v["operations"][0]["status"], OP_REJECTED)
        v2 = validate_proposal(_inv(), {"operations": [
            {"op": "add", "role": "supporting", "title": "from other run",
             "trace_id": "OTHER"},
        ]}, allow_other_trace=True)
        self.assertEqual(v2["operations"][0]["status"], OP_OK)

    def test_unknown_bookmark_and_op_rejected(self) -> None:
        v = validate_proposal(_inv(), {"operations": [
            {"op": "update", "bookmark_id": "NOPE", "changes": {"note": "x"}},
            {"op": "frobnicate"},
            {"op": "link", "from": "e1", "to": "NOPE"},
        ]})
        self.assertEqual([o["status"] for o in v["operations"]],
                         [OP_REJECTED, OP_REJECTED, OP_REJECTED])

    def test_model_secrets_stripped(self) -> None:
        v = validate_proposal(_inv(), {
            "model": {"model": "gpt-x", "provider": "openai", "api_key": "sk-SECRET",
                      "prompt": "system..."},
            "operations": [],
        })
        self.assertEqual(v["model"], {"model": "gpt-x", "provider": "openai"})
        self.assertEqual(v["schema"], PROPOSAL_SCHEMA)

    def test_strip_model_secrets_direct(self) -> None:
        self.assertEqual(
            strip_model_secrets({"model": "m", "api_key": "k", "authorization": "b"}),
            {"model": "m"},
        )


class ProposalApplyTests(unittest.TestCase):
    def _validated(self):
        return validate_proposal(_inv(), {
            "model": {"model": "gpt-x", "provider": "openai"},
            "operations": [
                {"op": "add", "role": "supporting", "title": "AI: affinity mask",
                 "author": "ai", "evidence_ids": ["e1"], "rationale": "based on e1"},
                {"op": "link", "from": "e1", "to": "h1", "relation": "supports"},
                {"op": "change_status", "status": "closed"},
                {"op": "update", "bookmark_id": "e1", "changes": {"value": 1}},
            ],
        })

    def test_only_accepted_ok_ops_apply(self) -> None:
        inv, applied, skipped = apply_proposal(
            _inv(), self._validated(), accept_all=True,
        )
        # 0 (add) + 1 (link) apply; 2 (close) needs confirm; 3 (measured update) rejected
        self.assertEqual(applied, [0, 1])
        self.assertEqual(sorted(skipped), [2, 3])
        ai = [b for b in inv["bookmarks"] if b.get("evidence", {}).get("author") == "ai"]
        self.assertEqual(len(ai), 1)
        self.assertNotEqual(ai[0]["evidence"]["kind"], "measured")
        self.assertEqual(
            ai[0]["evidence"]["ai_provenance"],
            {"model": "gpt-x", "provider": "openai", "source_evidence_ids": ["e1"]},
        )
        e1 = next(b for b in inv["bookmarks"] if b["id"] == "e1")
        self.assertEqual(e1["evidence"]["value"], 120)  # measured value untouched

    def test_confirmation_gates_close(self) -> None:
        v = self._validated()
        _no, applied_no, _ = apply_proposal(_inv(), v, accept_all=True)
        self.assertNotIn(2, applied_no)
        inv_yes, applied_yes, _ = apply_proposal(
            _inv(), v, accept_all=True, confirmed_indices=[2],
        )
        self.assertIn(2, applied_yes)
        self.assertEqual(inv_yes["status"], "closed")

    def test_proposal_events_recorded_without_secrets(self) -> None:
        inv, _applied, _ = apply_proposal(_inv(), self._validated(), accept_all=True,
                                          now="2026-09-08T12:00")
        ev = inv["proposal_events"][-1]
        self.assertEqual(ev["schema"], PROPOSAL_SCHEMA)
        self.assertEqual(ev["accepted"], [0, 1])
        self.assertEqual(ev["model"], {"model": "gpt-x", "provider": "openai"})
        self.assertEqual(ev["at"], "2026-09-08T12:00")

    def test_diff_is_grouped_by_section(self) -> None:
        d = proposal_diff(_inv(), self._validated())
        self.assertEqual([o["index"] for o in d["needs_confirmation"]], [2])
        self.assertEqual([o["index"] for o in d["rejected"]], [3])
        self.assertTrue(d["by_section"]["evidence"])
        self.assertTrue(d["by_section"]["links"])
        self.assertTrue(d["by_section"]["status"])

    def test_nothing_applies_by_default(self) -> None:
        # Empty accept list ⇒ nothing (no auto-apply).
        inv, applied, _ = apply_proposal(_inv(), self._validated(), accept_indices=[])
        self.assertEqual(applied, [])
        self.assertNotIn("proposal_events", inv)


class ArchitectureBoundaryTests(unittest.TestCase):
    def test_notebook_model_still_imports_no_ai(self) -> None:
        from pathlib import Path
        src = (Path(__file__).resolve().parents[1]
               / "btf_viewer_pkg" / "investigation_notebook.py").read_text(encoding="utf-8")
        self.assertNotIn("investigation_ai", src)
        self.assertNotIn("from .ai_", src)

    def test_desktop_web_lockstep(self) -> None:
        from pathlib import Path
        root = Path(__file__).resolve().parents[1]
        py = (root / "btf_viewer_pkg" / "investigation_ai.py").read_text(encoding="utf-8")
        js = (root / "web" / "src" / "utils" / "investigationAi.js").read_text(encoding="utf-8")
        for py_name, js_name in (
            ("def collaborate_context", "export function collaborateContext"),
            ("def collaborate_header", "export function collaborateHeader"),
            ("def nb_ai_action_reason", "export function nbAiActionReason"),
            ("def validate_proposal", "export function validateProposal"),
            ("def proposal_diff", "export function proposalDiff"),
            ("def apply_proposal", "export function applyProposal"),
            ("def strip_model_secrets", "export function stripModelSecrets"),
            ("PROPOSAL_SCHEMA", "export const PROPOSAL_SCHEMA"),
            ("NB_AI_ACTIONS", "export const NB_AI_ACTIONS"),
            ("NB_AI_DISABLED_REASON", "export const NB_AI_DISABLED_REASON"),
        ):
            self.assertIn(py_name, py, py_name)
            self.assertIn(js_name, js, js_name)
        # the six action ids match
        for aid in ("review_investigation", "suggest_next_check", "draft_hypotheses",
                    "draft_conclusion", "update_from_findings", "compare_trace"):
            self.assertIn(f'"{aid}"', py, aid)
            self.assertIn(f"'{aid}'", js, aid)


if __name__ == "__main__":
    unittest.main()
