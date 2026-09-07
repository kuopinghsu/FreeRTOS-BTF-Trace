"""Investigation Bookmarks and Evidence Chain — model, refs, chains, undo/redo,
serialisation, HTML export. Parity with ``web/tests/investigationNotebook.test.js``.
"""
from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace

BTF_ROOT = Path(__file__).resolve().parents[1]
if str(BTF_ROOT) not in sys.path:
    sys.path.insert(0, str(BTF_ROOT))

from btf_viewer_pkg.investigation_notebook import (  # noqa: E402
    BM_CONCLUSION,
    BM_HYPOTHESIS,
    BM_OBSERVATION,
    BM_SUPPORTING,
    BOOKMARK_TYPES,
    INVESTIGATION_SCHEMA,
    add_bookmark,
    add_unresolved_question,
    conclusion_evidence_chains,
    detect_broken_references,
    dump_investigation,
    empty_notebook_history,
    investigation_from_case,
    scaffold_investigation_from_findings,
    link_bookmarks,
    load_investigation,
    new_investigation,
    notebook_history_state,
    notebook_redo,
    notebook_undo,
    push_notebook_state,
    remove_bookmark,
    set_conclusion,
    trace_identity,
    update_bookmark,
)
from btf_viewer_pkg.stats_html import html_investigation_section  # noqa: E402


def _fake_trace(**over):
    base = dict(
        segments=[SimpleNamespace(start=0, end=10, core="Core_0")],
        sti_events=[],
        tasks=["Runner", "CS"],
        core_names=["Core_0", "Core_1"],
        time_scale="us",
        time_min=0,
        time_max=1000,
    )
    base.update(over)
    return SimpleNamespace(**base)


class ModelTests(unittest.TestCase):
    def test_new_investigation_shape(self):
        inv = new_investigation(title="X", analysis_range={"start": 1, "end": 9})
        self.assertEqual(inv["schema"], INVESTIGATION_SCHEMA)
        self.assertEqual(inv["analysis_range"], {"start": 1, "end": 9})
        self.assertEqual(inv["bookmarks"], [])

    def test_add_bookmark_assigns_id_and_seq(self):
        inv = add_bookmark(new_investigation(), type=BM_OBSERVATION, title="Runner late")
        b = inv["bookmarks"][0]
        self.assertTrue(b["id"])
        self.assertEqual(b["seq"], 1)
        self.assertEqual(inv["next_seq"], 2)

    def test_unknown_type_falls_back_to_observation(self):
        inv = add_bookmark(new_investigation(), type="nonsense", title="t")
        self.assertEqual(inv["bookmarks"][0]["type"], BM_OBSERVATION)

    def test_refs_are_normalised_by_kind(self):
        inv = add_bookmark(new_investigation(), type=BM_SUPPORTING, title="ev", refs=[
            {"kind": "finding", "id": "blocking", "label": "Off-CPU"},
            {"kind": "entity", "label": "CS"},
            {"kind": "range", "range": {"start": 10, "end": 20}},
            {"kind": "bogus"},
            "notadict",
        ])
        refs = inv["bookmarks"][0]["refs"]
        self.assertEqual(len(refs), 3)
        self.assertEqual(refs[0]["rule_id"], "blocking")
        self.assertEqual(refs[1]["entity"], "CS")
        self.assertEqual(refs[2]["range"], {"start": 10, "end": 20})

    def test_update_and_remove_bookmark_drops_links(self):
        inv = add_bookmark(new_investigation(), type=BM_OBSERVATION, title="a", bookmark_id="a")
        inv = add_bookmark(inv, type=BM_HYPOTHESIS, title="b", bookmark_id="b")
        inv = link_bookmarks(inv, "a", "b", "supports")
        inv = update_bookmark(inv, "a", title="a2", note="n")
        self.assertEqual(inv["bookmarks"][0]["title"], "a2")
        inv = remove_bookmark(inv, "b")
        self.assertEqual(len(inv["bookmarks"]), 1)
        self.assertEqual(inv["links"], [])

    def test_editing_returns_a_new_object(self):
        a = add_bookmark(new_investigation(), type=BM_OBSERVATION, title="x")
        b = set_conclusion(a, "done")
        self.assertEqual(a["conclusion"], "")
        self.assertEqual(b["conclusion"], "done")

    def test_link_requires_existing_distinct_bookmarks(self):
        inv = add_bookmark(new_investigation(), type=BM_OBSERVATION, title="a", bookmark_id="a")
        self.assertEqual(link_bookmarks(inv, "a", "a", "supports")["links"], [])
        self.assertEqual(link_bookmarks(inv, "a", "ghost", "supports")["links"], [])


class ChainTests(unittest.TestCase):
    def _case(self):
        inv = new_investigation(title="c")
        inv = add_bookmark(inv, type=BM_OBSERVATION, title="obs", bookmark_id="obs",
                           refs=[{"kind": "entity", "entity": "CS"}])
        inv = add_bookmark(inv, type=BM_SUPPORTING, title="sup", bookmark_id="sup",
                           refs=[{"kind": "finding", "rule_id": "blocking"}])
        inv = add_bookmark(inv, type=BM_HYPOTHESIS, title="hyp", bookmark_id="hyp")
        inv = add_bookmark(inv, type=BM_CONCLUSION, title="concl", bookmark_id="concl")
        inv = link_bookmarks(inv, "concl", "hyp", "concludes")
        inv = link_bookmarks(inv, "hyp", "sup", "supports")
        return inv

    def test_conclusion_reaches_evidence_via_links(self):
        chains = conclusion_evidence_chains(self._case())
        self.assertEqual(len(chains), 1)
        c = chains[0]
        self.assertTrue(c["grounded"])
        titles = {e["title"] for e in c["evidence"]}
        self.assertEqual(titles, {"hyp", "sup"})

    def test_shared_reference_also_links_evidence(self):
        inv = new_investigation()
        inv = add_bookmark(inv, type=BM_SUPPORTING, title="sup", bookmark_id="s",
                           refs=[{"kind": "entity", "entity": "Runner"}])
        inv = add_bookmark(inv, type=BM_CONCLUSION, title="c", bookmark_id="c",
                           refs=[{"kind": "entity", "entity": "Runner"}])
        chains = conclusion_evidence_chains(inv)
        self.assertTrue(chains[0]["grounded"])
        self.assertEqual(chains[0]["evidence"][0]["id"], "s")

    def test_isolated_conclusion_is_not_grounded(self):
        inv = add_bookmark(new_investigation(), type=BM_CONCLUSION, title="lonely")
        chains = conclusion_evidence_chains(inv)
        self.assertFalse(chains[0]["grounded"])

    def test_chains_are_deterministic(self):
        inv = self._case()
        self.assertEqual(
            conclusion_evidence_chains(inv), conclusion_evidence_chains(inv))


class BrokenReferenceTests(unittest.TestCase):
    def test_unknown_rule_id_flagged(self):
        inv = add_bookmark(new_investigation(), type=BM_SUPPORTING, title="e",
                           bookmark_id="e", refs=[{"kind": "finding", "rule_id": "gone"}])
        res = detect_broken_references(inv, known_rule_ids=["blocking", "thrashing"])
        self.assertEqual(len(res["issues"]), 1)
        self.assertEqual(res["issues"][0]["bookmark_id"], "e")

    def test_entity_and_range_checked_against_trace(self):
        inv = add_bookmark(new_investigation(), type=BM_OBSERVATION, title="o", refs=[
            {"kind": "entity", "entity": "Ghost"},
            {"kind": "range", "range": {"start": 5, "end": 5000}},
        ])
        res = detect_broken_references(inv, trace=_fake_trace())
        reasons = {i["reason"] for i in res["issues"]}
        self.assertTrue(any("entity" in r for r in reasons))
        self.assertTrue(any("span" in r for r in reasons))

    def test_stale_trace_flag_on_identity_mismatch(self):
        t1 = trace_identity(_fake_trace(), "a.btf")
        inv = new_investigation(trace_identity=t1)
        t2 = trace_identity(_fake_trace(tasks=["Runner", "CS", "Extra"]), "a.btf")
        self.assertTrue(detect_broken_references(inv, current_identity=t2)["stale_trace"])
        self.assertFalse(detect_broken_references(inv, current_identity=t1)["stale_trace"])

    def test_clean_investigation_has_no_issues(self):
        inv = add_bookmark(new_investigation(), type=BM_SUPPORTING, title="ok", refs=[
            {"kind": "finding", "rule_id": "blocking"},
            {"kind": "entity", "entity": "CS"},
            {"kind": "range", "range": {"start": 10, "end": 500}},
        ])
        res = detect_broken_references(
            inv, trace=_fake_trace(), known_rule_ids=["blocking"])
        self.assertEqual(res["issues"], [])

    def test_entity_ref_resolves_across_decorated_forms(self):
        # A trace like the parser produces: merge-key task list + task_repr with
        # decorated raw reprs. An entity ref stored in *any* spelling (Web
        # display label, Desktop merge key, bare name, anonymized Task-N) must
        # still resolve — this is what caused "1 stale ref" after a Web→Desktop
        # Anonymize export.
        tr = SimpleNamespace(
            tasks=["\x001\x00Runner", "\x005\x00CS"],
            task_repr={"\x001\x00Runner": "[0/0001]Runner",
                       "\x005\x00CS": "[0/0005]CS"},
            core_names=["Core_0", "Core_1"], time_min=0, time_max=1000)
        for ent in ("Runner", "Runner[1]", "[0/0001]Runner", "\x001\x00Runner"):
            inv = add_bookmark(new_investigation(), type=BM_OBSERVATION,
                               title="o", refs=[{"kind": "entity", "entity": ent}])
            self.assertEqual(
                detect_broken_references(inv, trace=tr)["issues"], [], ent)
        # A name that is genuinely gone is still flagged.
        inv = add_bookmark(new_investigation(), type=BM_OBSERVATION, title="o",
                           refs=[{"kind": "entity", "entity": "GhostTask"}])
        self.assertEqual(len(detect_broken_references(inv, trace=tr)["issues"]), 1)


class UndoRedoTests(unittest.TestCase):
    def test_push_undo_redo(self):
        inv = new_investigation()
        h = push_notebook_state(empty_notebook_history(), inv)
        h = push_notebook_state(h, set_conclusion(inv, "one"))
        h = push_notebook_state(h, add_bookmark(inv, type=BM_OBSERVATION, title="o"))
        st = notebook_history_state(h)
        self.assertEqual(st["count"], 3)
        self.assertTrue(st["can_undo"])
        self.assertFalse(st["can_redo"])

        h = notebook_undo(h)
        st = notebook_history_state(h)
        self.assertEqual(st["current"]["conclusion"], "one")
        self.assertTrue(st["can_redo"])

        h = notebook_undo(h)
        self.assertFalse(notebook_history_state(h)["can_undo"])

        h = notebook_redo(h)
        self.assertEqual(notebook_history_state(h)["current"]["conclusion"], "one")

    def test_push_after_undo_truncates_redo_branch(self):
        inv = new_investigation()
        h = push_notebook_state(empty_notebook_history(), inv)
        h = push_notebook_state(h, set_conclusion(inv, "a"))
        h = push_notebook_state(h, set_conclusion(inv, "b"))
        h = notebook_undo(h)                     # back to "a"
        h = push_notebook_state(h, set_conclusion(inv, "c"))
        st = notebook_history_state(h)
        self.assertEqual(st["count"], 3)         # b dropped
        self.assertFalse(st["can_redo"])
        self.assertEqual(st["current"]["conclusion"], "c")

    def test_identical_state_is_not_pushed_twice(self):
        inv = add_bookmark(new_investigation(), type=BM_OBSERVATION, title="o")
        h = push_notebook_state(empty_notebook_history(), inv)
        h = push_notebook_state(h, load_investigation(dump_investigation(inv)))
        self.assertEqual(notebook_history_state(h)["count"], 1)


class SerialisationTests(unittest.TestCase):
    def _rich(self):
        inv = new_investigation(title="T", analysis_range={"start": 0, "end": 100})
        inv = add_bookmark(inv, type=BM_OBSERVATION, title="o", bookmark_id="o",
                           refs=[{"kind": "range", "range": {"start": 1, "end": 9}}])
        inv = add_bookmark(inv, type=BM_CONCLUSION, title="c", bookmark_id="c")
        inv = link_bookmarks(inv, "c", "o", "concludes")
        inv = set_conclusion(inv, "final")
        inv = add_unresolved_question(inv, "why?")
        return inv

    def test_round_trip_is_stable(self):
        inv = self._rich()
        once = dump_investigation(inv)
        twice = dump_investigation(load_investigation(once))
        self.assertEqual(once, twice)

    def test_load_repairs_bad_input(self):
        loaded = load_investigation({
            "bookmarks": [
                {"type": "weird", "title": "a"},
                "notadict",
                {"title": "b", "type": "hypothesis", "id": "dup"},
                {"title": "c", "type": "hypothesis", "id": "dup"},
            ],
            "links": [{"from": "dup", "to": "missing", "relation": "x"}],
            "unresolved_questions": ["  ", "keep"],
        })
        self.assertEqual(loaded["bookmarks"][0]["type"], "observation")
        ids = [b["id"] for b in loaded["bookmarks"]]
        self.assertEqual(len(ids), len(set(ids)))          # de-duplicated
        self.assertEqual(loaded["links"], [])              # dangling link dropped
        self.assertEqual(loaded["unresolved_questions"], ["keep"])
        self.assertEqual(loaded["schema"], INVESTIGATION_SCHEMA)

    def test_load_preserves_unknown_keys(self):
        loaded = load_investigation({"title": "x", "_future": {"k": 1}})
        self.assertEqual(loaded["_future"], {"k": 1})

    def test_load_from_json_text(self):
        inv = self._rich()
        self.assertEqual(
            load_investigation(dump_investigation(inv))["title"], "T")


class CaseBridgeTests(unittest.TestCase):
    def test_case_findings_become_supporting_bookmarks(self):
        findings = [
            {"id": "blocking", "rule_id": "blocking", "severity": "warning",
             "title": "Off-CPU spikes", "observation": "CS off-CPU 3ms",
             "entities": ["CS"], "affected_range": {"start": 10, "end": 90},
             "inspect": "Off-CPU Time (Blocking Time)"},
            {"id": "thrashing", "rule_id": "thrashing", "severity": "warning",
             "title": "Excessive core migration", "entities": ["Worker"]},
        ]
        inv = investigation_from_case(
            case_finding_ids=["blocking"], findings=findings,
            analysis_range={"start": 0, "end": 100}, title="Case A")
        self.assertEqual(len(inv["bookmarks"]), 1)
        b = inv["bookmarks"][0]
        self.assertEqual(b["type"], BM_SUPPORTING)
        kinds = {r["kind"] for r in b["refs"]}
        self.assertEqual(kinds, {"finding", "entity", "range", "metric"})

    def test_missing_case_id_is_skipped(self):
        inv = investigation_from_case(case_finding_ids=["ghost"], findings=[])
        self.assertEqual(inv["bookmarks"], [])


class ScaffoldTests(unittest.TestCase):
    _FINDINGS = [
        {"id": "top_cpu", "rule_id": "top_cpu", "severity": "warning",
         "title": "High CPU on Med", "text": "Med 17%", "entities": ["Med"],
         "affected_range": {"start": 10, "end": 99}, "inspect": "Top Tasks by CPU"},
        {"id": "wcet", "rule_id": "wcet", "severity": "error",
         "title": "WCET outlier", "entities": ["Runner"], "inspect": "Execution Time"},
        {"id": "none", "rule_id": "none", "severity": "info",
         "title": "No findings under the current rules"},
    ]

    def test_seeds_observations_plus_stubs_when_empty(self):
        inv = scaffold_investigation_from_findings(
            new_investigation(title="T"), findings=self._FINDINGS,
            cursor_range={"start": 5, "end": 50})
        types = [b["type"] for b in inv["bookmarks"]]
        # error sorts before warning; info "no findings" excluded; + 2 stubs
        self.assertEqual(types, ["observation", "observation", "hypothesis", "verification"])
        self.assertEqual(inv["bookmarks"][0]["title"], "WCET outlier")
        # WCET has no affected_range → cursor_range is used
        kinds = {r["kind"] for r in inv["bookmarks"][0]["refs"]}
        self.assertEqual(kinds, {"finding", "entity", "range", "metric"})

    def test_is_idempotent_and_no_extra_stubs_on_rerun(self):
        inv = scaffold_investigation_from_findings(
            new_investigation(), findings=self._FINDINGS)
        n = len(inv["bookmarks"])
        inv2 = scaffold_investigation_from_findings(inv, findings=self._FINDINGS)
        self.assertEqual(len(inv2["bookmarks"]), n)

    def test_include_info_and_limit(self):
        inv = scaffold_investigation_from_findings(
            new_investigation(), findings=self._FINDINGS, include_info=True, limit=1)
        obs = [b for b in inv["bookmarks"] if b["type"] == "observation"]
        self.assertEqual(len(obs), 1)


class HtmlSectionTests(unittest.TestCase):
    def _inv(self):
        inv = new_investigation(title="Runner stall", analysis_range={"start": 0, "end": 1000})
        inv = add_bookmark(inv, type=BM_OBSERVATION, title="Runner misses period",
                           bookmark_id="obs", note="at 500us",
                           refs=[{"kind": "range", "range": {"start": 400, "end": 600}}])
        inv = add_bookmark(inv, type=BM_HYPOTHESIS, title="Mutex held too long", bookmark_id="hyp")
        inv = add_bookmark(inv, type=BM_SUPPORTING, title="CS holds 300us", bookmark_id="sup",
                           refs=[{"kind": "finding", "rule_id": "blocking"}])
        inv = add_bookmark(inv, type=BM_CONCLUSION, title="Priority inversion", bookmark_id="con")
        inv = link_bookmarks(inv, "con", "hyp", "concludes")
        inv = link_bookmarks(inv, "hyp", "sup", "supports")
        inv = add_unresolved_question(inv, "Why so long?")
        return inv

    def test_section_groups_and_chain(self):
        inv = self._inv()
        html = html_investigation_section(
            inv, format_ns=lambda ns: f"{ns}us",
            chains=conclusion_evidence_chains(inv), scope_title=" (C1–C2)")
        self.assertIn("<h2>Investigation (C1–C2)</h2>", html)
        for label in ("Facts", "Hypotheses", "Conclusions", "Unresolved questions"):
            self.assertIn(f"{label}</h3>", html)
        self.assertIn("Backed by:", html)
        self.assertIn("CS holds 300us", html)
        # exactly one outer <section> so the report TOC wrapper stays valid
        self.assertEqual(html.count("<section"), 1)
        self.assertEqual(html.count("</section>"), 1)

    def test_section_shows_stale_reference(self):
        inv = self._inv()
        broken = {"stale_trace": True, "issues": [
            {"bookmark_id": "obs", "ref_index": 0, "kind": "range",
             "reason": "time range falls outside the trace span"}]}
        html = html_investigation_section(inv, broken_refs=broken)
        self.assertIn("Stale:", html)
        self.assertIn("source trace changed", html)

    def test_empty_investigation_renders_nothing(self):
        self.assertEqual(html_investigation_section(new_investigation()), "")
        self.assertEqual(html_investigation_section(None), "")


class ParityTests(unittest.TestCase):
    def test_module_and_js_in_step(self):
        py = (BTF_ROOT / "btf_viewer_pkg" / "investigation_notebook.py").read_text("utf-8")
        js = (BTF_ROOT / "web" / "src" / "utils" / "investigationNotebook.js").read_text("utf-8")
        for t in BOOKMARK_TYPES:
            self.assertIn(f'"{t}"', py)
            self.assertIn(f"'{t}'", js)
        for py_name, js_name in (
            ("def new_investigation", "export function newInvestigation"),
            ("def add_bookmark", "export function addBookmark"),
            ("def link_bookmarks", "export function linkBookmarks"),
            ("def detect_broken_references", "export function detectBrokenReferences"),
            ("def _entity_bare", "export function entityBare"),
            ("def _entity_vocabulary", "function entityVocabulary"),
            ("def conclusion_evidence_chains", "export function conclusionEvidenceChains"),
            ("def dump_investigation", "export function dumpInvestigation"),
            ("def load_investigation", "export function loadInvestigation"),
            ("def push_notebook_state", "export function pushNotebookState"),
            ("def investigation_from_case", "export function investigationFromCase"),
            ("def scaffold_investigation_from_findings",
             "export function scaffoldInvestigationFromFindings"),
            ("INVESTIGATION_SCHEMA", "export const INVESTIGATION_SCHEMA"),
        ):
            self.assertIn(py_name, py, py_name)
            self.assertIn(js_name, js, js_name)


if __name__ == "__main__":
    unittest.main()
