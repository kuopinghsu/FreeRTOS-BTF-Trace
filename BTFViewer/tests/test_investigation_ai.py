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
    collaborate_digest,
    collaborate_header,
    nb_ai_action_reason,
    parse_question_suggestion,
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
    def test_eight_focused_actions(self) -> None:
        # + gather_evidence (agentic tool loop) after review. Lockstep with
        # web/tests/investigationAi.test.js's "eight focused actions" test.
        self.assertEqual(
            [a[0] for a in NB_AI_ACTIONS],
            ["review_investigation", "gather_evidence", "suggest_next_check",
             "draft_hypotheses", "draft_conclusion", "update_from_findings",
             "compare_trace", "refine_question"],
        )

    def test_refine_question_suggestion_parsing(self) -> None:
        # Bypasses the proposal machinery entirely. Lockstep with web/tests/
        # investigationAi.test.js's "refine_question suggestion parsing" block.
        self.assertEqual(
            parse_question_suggestion("Suggested question: Why does ControlTask stall?"),
            "Why does ControlTask stall?")
        self.assertEqual(
            parse_question_suggestion("suggested question:  Why does it stall before dispatch?  "),
            "Why does it stall before dispatch?")
        self.assertEqual(
            parse_question_suggestion('Suggested question: "Why does it stall?"'),
            "Why does it stall?")
        self.assertEqual(
            parse_question_suggestion("Here is a general review of your investigation."), "")
        self.assertEqual(parse_question_suggestion(""), "")
        self.assertEqual(parse_question_suggestion(None), "")

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

    def test_digest_is_readable_markdown_not_json(self) -> None:
        ctx = collaborate_context(_inv(), action="review_investigation")
        d = collaborate_digest(ctx)
        # readable section headers, the evidence line, and no JSON punctuation soup
        self.assertIn("**Question**", d)
        self.assertIn("**Evidence (1)**", d)
        self.assertIn("120 migrations", d)
        self.assertIn("**Conclusion**", d)
        self.assertNotIn("{", d)
        self.assertNotIn('"bookmark_id"', d)
        # empty / bad input is a harmless empty-ish string, never a throw
        self.assertIsInstance(collaborate_digest(None), str)


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

    def test_ai_can_add_a_hypothesis(self) -> None:
        # Demo parity: the aside's "Add hypothesis" action. A hypothesis add
        # is accepted (no evidence card), routes to the Hypotheses group, and
        # links each cited evidence id as "supports" on apply.
        v = validate_proposal(_inv(), {"operations": [
            {"op": "add", "role": "Hypothesis",
             "title": "Affinity thrash on core 1", "evidence_ids": ["e1"]},
        ]})
        self.assertEqual(v["operations"][0]["status"], OP_OK)
        self.assertNotIn("reason", v["operations"][0])
        d = proposal_diff(_inv(), v)
        self.assertEqual(len(d["by_section"]["hypotheses"]), 1)
        self.assertEqual(len(d["by_section"]["evidence"]), 0)

        v2 = validate_proposal(_inv(), {"operations": [
            {"op": "add", "role": "hypothesis", "title": "no citation"},
        ]})
        self.assertEqual(v2["operations"][0]["status"], OP_OK)
        self.assertIn("cites no evidence id", v2["operations"][0]["reason"])

        v3 = validate_proposal(_inv(), {"operations": [
            {"op": "add", "role": "hypothesis", "title": "Affinity thrash",
             "note": "from E1", "evidence_ids": ["e1", "missing"]},
        ]})
        out, applied, _ = apply_proposal(_inv(), v3, accept_all=True)
        self.assertEqual(applied, [0])
        hyp = next(b for b in out["bookmarks"]
                   if b["type"] == "hypothesis" and b["title"] == "Affinity thrash")
        self.assertNotIn("evidence", hyp)
        self.assertTrue(any(
            str(link["from"]) == "e1" and str(link["to"]) == str(hyp["id"])
            and link["relation"] == "supports"
            for link in out.get("links") or []))
        self.assertFalse(any(str(link["from"]) == "missing"
                             for link in out.get("links") or []))

    def test_malformed_add_role_still_rejected(self) -> None:
        v = validate_proposal(_inv(), {"operations": [
            {"op": "add", "role": "not_a_role", "title": "x"},
        ]})
        self.assertEqual(v["operations"][0]["status"], OP_REJECTED)
        self.assertIn("evidence or hypothesis role", v["operations"][0]["reason"])

    def test_structured_reply_carries_summary_and_notes(self) -> None:
        v = validate_proposal(_inv(), {
            "schema": "btf-viewer-nb-proposal/1",
            "summary": "  Two claims are unsupported.  ",
            "notes": ["Max slice is treated as WCET", "",
                      "  Migration count has no latency link  ", None],
            "operations": [],
        })
        self.assertFalse(v["ok"])
        self.assertEqual(v["summary"], "Two claims are unsupported.")
        self.assertEqual(
            v["notes"],
            ["Max slice is treated as WCET", "Migration count has no latency link"])

    def test_every_non_refine_prompt_demands_the_json_envelope(self) -> None:
        prompts = {a[0]: a[2] for a in NB_AI_ACTIONS}
        for aid in ("review_investigation", "gather_evidence", "suggest_next_check", "draft_hypotheses",
                    "draft_conclusion", "update_from_findings", "compare_trace"):
            self.assertIn("btf-viewer-nb-proposal/1", prompts[aid], aid)
            self.assertIn('"operations"', prompts[aid], aid)
        self.assertNotIn("btf-viewer-nb-proposal", prompts["refine_question"])

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
            ("def collaborate_digest", "export function collaborateDigest"),
            ("def nb_ai_action_reason", "export function nbAiActionReason"),
            ("def validate_proposal", "export function validateProposal"),
            ("def proposal_diff", "export function proposalDiff"),
            ("def apply_proposal", "export function applyProposal"),
            ("def strip_model_secrets", "export function stripModelSecrets"),
            ("def parse_question_suggestion", "export function parseQuestionSuggestion"),
            ("def parse_reply_blocks", "export function parseReplyBlocks"),
            ("def extract_notebook_proposal", "export function extractNotebookProposal"),
            ("def summarize_notebook_proposal_for_chat",
             "export function summarizeNotebookProposalForChat"),
            ("PROPOSAL_SCHEMA", "export const PROPOSAL_SCHEMA"),
            ("NB_AI_ACTIONS", "export const NB_AI_ACTIONS"),
            ("NB_PROPOSAL_REPLY_FORMAT", "export const NB_PROPOSAL_REPLY_FORMAT"),
            ("NB_AI_DISABLED_REASON", "export const NB_AI_DISABLED_REASON"),
        ):
            self.assertIn(py_name, py, py_name)
            self.assertIn(js_name, js, js_name)
        # the eight action ids match
        for aid in ("review_investigation", "gather_evidence", "suggest_next_check", "draft_hypotheses",
                    "draft_conclusion", "update_from_findings", "compare_trace"):
            self.assertIn(f'"{aid}"', py, aid)
            self.assertIn(f"'{aid}'", js, aid)
        # …and the prompt *text* stays in lockstep (name-only checks let the
        # NB_PROPOSAL_REPLY_FORMAT wording drift once — this catches it). Each
        # phrase sits inside a single JS string literal / single .py line.
        for phrase in (
            "NOTHING before or after it",              # NB_PROPOSAL_REPLY_FORMAT
            "do NOT put it inside a markdown",         # NB_PROPOSAL_REPLY_FORMAT
            'Use "operations":[] when you are only reviewing',
            "CALLING BTFViewer tools",                 # gather_evidence
            "one round per gap",                       # gather_evidence
            "Derived-strength evidence",               # review_investigation
        ):
            self.assertIn(phrase, js, f"web NB prompt missing: {phrase!r}")
            self.assertIn(phrase, py, f"desktop NB prompt missing: {phrase!r}")


class ReplyBlocksTests(unittest.TestCase):
    """parse_reply_blocks — prose AI reply → titled sections + bullets.
    Parity with web/tests/investigationAi.test.js's parseReplyBlocks block."""

    def test_headings_become_titled_sections(self) -> None:
        from btf_viewer_pkg.investigation_ai import parse_reply_blocks
        blocks = parse_reply_blocks(
            "### 結論\nTwo claims are unsupported.\n\n"
            "### Unsupported Claims\n1. **Max slice** is treated as WCET\n"
            "- Migration count has no latency link")
        self.assertEqual([b["title"] for b in blocks],
                         ["結論", "Unsupported Claims"])
        self.assertEqual(blocks[0]["items"], ["Two claims are unsupported."])
        self.assertEqual(
            blocks[1]["items"],
            ["Max slice is treated as WCET", "Migration count has no latency link"])

    def test_bold_line_heading_plain_prose_and_empty(self) -> None:
        from btf_viewer_pkg.investigation_ai import parse_reply_blocks
        self.assertEqual(parse_reply_blocks("**Findings:**\nfoo\nbar"),
                         [{"title": "Findings", "items": ["foo", "bar"]}])
        self.assertEqual(parse_reply_blocks("just one line"),
                         [{"title": "", "items": ["just one line"]}])
        self.assertEqual(parse_reply_blocks(""), [])
        self.assertEqual(parse_reply_blocks(None), [])


class ExtractNotebookProposalTests(unittest.TestCase):
    """extract_notebook_proposal — tolerant of how the model wraps the JSON.
    Parity with web/tests/investigationAi.test.js's extractNotebookProposal."""

    OBJ = ('{"schema":"btf-viewer-nb-proposal/1","summary":"only one measured item",'
           '"notes":["no hypotheses"],"operations":[{"op":"add","role":"observation",'
           '"title":"Check Mutex Blocking","note":"open the section","evidence_ids":["E1"]}]}')

    def test_plain_fenced_block(self) -> None:
        from btf_viewer_pkg.investigation_ai import extract_notebook_proposal
        p = extract_notebook_proposal("```json\n" + self.OBJ + "\n```")
        self.assertEqual(p["summary"], "only one measured item")
        self.assertEqual(len(p["operations"]), 1)

    def test_object_inside_a_markdown_list_with_trailing_prose(self) -> None:
        from btf_viewer_pkg.investigation_ai import extract_notebook_proposal
        reply = "\n".join((
            "AI reply", "", "* ```json", "* " + self.OBJ, "* ```",
            "* Investigate the current finding. [Run](btfnext:text/0)",
            "* Investigate remaining finding [Open Statistics](btfstats:section/block)",
        ))
        p = extract_notebook_proposal(reply)
        self.assertIsNotNone(p)
        self.assertEqual(p["operations"][0]["title"], "Check Mutex Blocking")
        self.assertEqual(p["notes"], ["no hypotheses"])

    def test_bare_unfenced_object_in_prose_and_review_only_and_none(self) -> None:
        from btf_viewer_pkg.investigation_ai import extract_notebook_proposal
        p = extract_notebook_proposal("Here is my analysis: " + self.OBJ + " — done.")
        self.assertEqual(p["summary"], "only one measured item")
        review = extract_notebook_proposal(
            '```json\n{"schema":"btf-viewer-nb-proposal/1","summary":"s","notes":["a"]}\n```')
        self.assertEqual(review["operations"], [])
        self.assertIsNone(extract_notebook_proposal("just a normal chat answer"))
        self.assertIsNone(extract_notebook_proposal(""))
        self.assertIsNone(extract_notebook_proposal(None))


class SummarizeNotebookProposalTests(unittest.TestCase):
    """summarize_notebook_proposal_for_chat — readable summary in the AI panel.
    Parity with web/tests/investigationAi.test.js."""

    OBJ = ('{"schema":"btf-viewer-nb-proposal/1","summary":"Only one measured item.",'
           '"notes":["No hypotheses yet","Conclusion is empty"],"operations":['
           '{"op":"add","role":"observation","title":"Check Mutex Blocking","note":"x","evidence_ids":["E2"]},'
           '{"op":"add","role":"observation","title":"Exec Time Max","note":"y","evidence_ids":["E6"]}]}')

    def test_list_wrapped_proposal_and_link_soup_become_a_summary(self) -> None:
        from btf_viewer_pkg.investigation_ai import summarize_notebook_proposal_for_chat
        reply = "\n".join((
            "* ```json", "* " + self.OBJ, "* ```",
            "* Investigate the current finding [Run](btfnext:text/0)",
            "* Investigate remaining finding [Open Statistics](btfstats:section/block)",
        ))
        s = summarize_notebook_proposal_for_chat(reply)
        self.assertNotIn("btf-viewer-nb-proposal", s)
        self.assertNotIn("btfnext:", s)
        self.assertNotIn("```", s)
        self.assertIn("**AI proposal for the Investigation Notebook**", s)
        self.assertIn("Only one measured item.", s)
        self.assertIn("- No hypotheses yet", s)
        self.assertIn("2 changes proposed", s)

    def test_review_only_and_passthrough(self) -> None:
        from btf_viewer_pkg.investigation_ai import summarize_notebook_proposal_for_chat
        s = summarize_notebook_proposal_for_chat(
            '```json\n{"schema":"btf-viewer-nb-proposal/1","summary":"s","notes":["a"]}\n```')
        self.assertIn("Review only", s)
        self.assertNotIn('"schema"', s)
        self.assertEqual(summarize_notebook_proposal_for_chat("plain answer"), "plain answer")
        self.assertEqual(summarize_notebook_proposal_for_chat(""), "")

    def test_ai_assistant_message_body_uses_the_summarizer(self) -> None:
        from pathlib import Path
        src = (Path(__file__).resolve().parents[1]
               / "btf_viewer_pkg" / "ai_assistant.py").read_text(encoding="utf-8")
        self.assertIn("from .investigation_ai import summarize_notebook_proposal_for_chat", src)
        body = src[src.index("def _ai_message_body_html"):src.index("def _ai_message_body_html") + 900]
        self.assertIn("summarize_notebook_proposal_for_chat(body_text)", body)


if __name__ == "__main__":
    unittest.main()
