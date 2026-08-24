"""Investigation Case, validator, quality, and offline AI benchmark."""
from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path

BTF_ROOT = Path(__file__).resolve().parents[1]
if str(BTF_ROOT) not in sys.path:
    sys.path.insert(0, str(BTF_ROOT))

from btf_viewer_pkg.ai_case import (  # noqa: E402
    accumulate_cost,
    builtin_investigation_templates,
    build_investigation_case,
    build_validation_catalog,
    classify_trace_privacy,
    clamp_ai_split_bottom,
    compact_chat_history,
    compact_findings_text,
    compact_tool_result_payload,
    compute_evidence_quality,
    dump_user_investigation_templates,
    dump_investigation_session,
    parse_investigation_session,
    empty_cost_meter,
    enrich_hypotheses,
    evidence_quality_band,
    falsification_checks,
    format_capability_report,
    format_context_usage_status,
    format_cost_status,
    historical_knowledge_for_finding,
    infer_model_capability,
    interpret_investigation_query,
    normalize_ai_context_mode,
    ai_context_mode_settings_overview,
    tool_names_for_context_mode,
    investigation_guide_stage,
    investigation_issue_card,
    format_investigation_issue_card,
    investigation_mode_prompt,
    load_benchmark_dataset,
    load_benchmark_suite_xml,
    match_historical_knowledge,
    new_user_investigation_template,
    parse_user_investigation_templates,
    quality_bar,
    benchmark_model_category,
    parse_live_benchmark_models,
    parse_benchmark_context_modes,
    select_benchmark_cases,
    select_benchmark_suite_models,
    benchmark_prompt_context,
    format_benchmark_markdown,
    merge_benchmark_report,
    parse_benchmark_markdown,
    run_live_benchmark,
    run_offline_benchmark,
    score_adversarial_metrics,
    score_benchmark_case,
    set_hypothesis_status,
    status_with_cost,
    validate_ai_response,
    validate_experiment,
)
from btf_viewer_pkg.ai_investigation import (  # noqa: E402
    build_investigate_context,
    extract_evidence_panel_payload,
    format_evidence_panel_markdown,
)


class InvestigationCaseTests(unittest.TestCase):
    def test_enrich_hypotheses_supported_when_times_present(self) -> None:
        hyps = enrich_hypotheses(
            [{"hypothesis": "Core thrashing / lock bounce", "why": "High migration"}],
            evidence=[{"label": "migrations: burst", "time": 1083}],
        )
        self.assertEqual(hyps[0]["status"], "supported")
        self.assertGreaterEqual(hyps[0]["confidence"], 70)

    def test_investigation_guide_stage_and_issue_card(self) -> None:
        self.assertEqual(investigation_guide_stage(None), "idle")
        self.assertEqual(
            investigation_guide_stage({"finding": {"title": "x"}}),
            "triage",
        )
        self.assertEqual(
            investigation_guide_stage(
                {"finding": {"title": "x"}}, has_cursors=True,
            ),
            "scope",
        )
        self.assertEqual(
            investigation_guide_stage(
                {"evidence": [{"label": "m", "time": 1}]},
            ),
            "investigate",
        )
        self.assertEqual(
            investigation_guide_stage(
                {"tools_executed": ["verify_claim"]},
            ),
            "verify",
        )
        self.assertEqual(
            investigation_guide_stage(
                {"tools_executed": ["what_if"]},
            ),
            "verify",
        )
        self.assertEqual(
            investigation_guide_stage(
                {"tools_executed": ["verify_claim", "what_if"]},
            ),
            "experiment",
        )
        self.assertEqual(
            investigation_guide_stage(
                {"tools_executed": ["compare_performance"]},
                has_two_traces=True,
            ),
            "compare",
        )
        card = investigation_issue_card({
            "finding": {"title": "Queue bounce", "task": "CS[1]"},
            "evidence_quality": {"band": "medium-high"},
        })
        self.assertEqual(card["title"], "Queue bounce")
        self.assertEqual(card["task"], "CS[1]")
        self.assertIn("Medium", card["band"])
        self.assertEqual(
            format_investigation_issue_card(card),
            "CURRENT ISSUE\nQueue bounce · CS[1] · Evidence Medium High",
        )
        self.assertEqual(format_investigation_issue_card(None), "")

    def test_dump_parse_investigation_session(self) -> None:
        blob = dump_investigation_session(
            payload={"finding": {"title": "x"}},
            plan={"goal": "g", "steps": []},
            messages=[{"role": "user", "content": "hello"}],
        )
        parsed = parse_investigation_session(blob)
        self.assertEqual(parsed["payload"]["finding"]["title"], "x")
        self.assertEqual(parsed["plan"]["goal"], "g")
        self.assertEqual(parsed["messages"][0]["content"], "hello")
        self.assertEqual(parse_investigation_session("")["messages"], [])
        from btf_viewer_pkg.ai_case import investigation_session_has_chat
        self.assertTrue(investigation_session_has_chat(parsed["messages"]))
        self.assertFalse(investigation_session_has_chat([]))
        self.assertFalse(investigation_session_has_chat(
            [{"role": "evidence", "content": "CURRENT ISSUE"}]))

    def test_analysis_dashboard_clusters_and_quality(self) -> None:
        from btf_viewer_pkg.ai_planner import analysis_dashboard
        dash = analysis_dashboard(
            [
                {"id": "f1", "severity": "warning", "title": "Core thrashing",
                 "text": "CS[1] migrates", "task": "CS[1]"},
                {"id": "f2", "severity": "error", "title": "Bounce",
                 "text": "CS[1] ping-pong", "task": "CS[1]"},
            ],
            quality_warnings=["Trace ring buffer overflow — oldest events may be missing."],
        )
        self.assertIn("Trace quality:", dash["summary"])
        self.assertGreaterEqual(dash["errors"], 1)
        self.assertTrue(dash["clusters"])

    def test_set_hypothesis_status_rejects(self) -> None:
        hyps = enrich_hypotheses(
            [{"hypothesis": "A", "why": "x"}, {"hypothesis": "B", "why": "y"}],
        )
        out = set_hypothesis_status(hyps, hyps[1]["id"], "rejected")
        self.assertEqual(out[1]["status"], "rejected")

    def test_build_case_from_investigate_context(self) -> None:
        ctx = build_investigate_context(
            [{"id": "f1", "severity": "warning",
              "title": "Excessive bouncing / core thrashing",
              "text": "CS[22] migrates heavily",
              "evidence": [{"label": "migrations: burst", "time": 1.08}]}],
            "f1",
        )
        case = build_investigation_case(ctx)
        self.assertEqual(case["schema"], "btf-investigation-case")
        self.assertTrue(case["hypotheses"])
        self.assertIn(case["evidence_quality"]["band"], (
            "strong", "medium-high", "medium", "weak", "insufficient",
        ))
        self.assertTrue(case["falsification"]["would_disprove"])
        self.assertTrue(case["falsification"]["supporting"])
        self.assertTrue(any("migrations" in s for s in case["falsification"]["supporting"]))
        self.assertTrue(case["evidence_graph"]["nodes"])

    def test_quality_bar_is_not_a_percent(self) -> None:
        self.assertIn("Strong", quality_bar("strong"))
        self.assertNotIn("%", quality_bar("strong"))
        self.assertEqual(evidence_quality_band(82), "strong")
        q = compute_evidence_quality(
            score=82,
            evidence=[{"time": 1, "label": "migrations: x"},
                      {"time": 2, "label": "blocking: y"}],
        )
        self.assertEqual(q["band"], "strong")
        self.assertTrue(q["flags"]["direct_evidence"])

    def test_status_with_cost_accumulates_and_hides_when_empty(self) -> None:
        self.assertEqual(status_with_cost("Done.", empty_cost_meter()), "Done.")
        meter = accumulate_cost(
            empty_cost_meter(),
            prompt_tokens=1000,
            completion_tokens=200,
            tool_calls=2,
            trace_queries=1,
            model_time_s=1.5,
        )
        meter = accumulate_cost(meter, prompt_tokens=50, completion_tokens=10)
        text = status_with_cost("Done.", meter)
        self.assertEqual(text, "Done. · 1.3k tok · 2 tools · 1.5s")
        self.assertEqual(format_cost_status(empty_cost_meter()), "0 tok · 0 tools · 0s")
        self.assertEqual(
            format_context_usage_status(empty_cost_meter(), "compact"),
            "Context: Compact",
        )
        self.assertEqual(
            format_context_usage_status(meter, "compact"),
            "Context: Compact · 1.3k tok · 2 tools · 1.5s",
        )
        self.assertEqual(
            format_context_usage_status(meter, "balanced"),
            "Context: Balanced · 1.3k tok · 2 tools · 1.5s",
        )
        shown = format_context_usage_status(meter, "balanced")
        self.assertNotIn("input", shown)
        self.assertNotIn("output", shown)
        self.assertEqual(clamp_ai_split_bottom(""), 80)
        self.assertEqual(clamp_ai_split_bottom(40), 64)
        self.assertEqual(clamp_ai_split_bottom(900), 400)

    def test_context_mode_compacts_findings_tools_and_history(self) -> None:
        self.assertEqual(normalize_ai_context_mode(""), "balanced")
        self.assertEqual(normalize_ai_context_mode("Full evidence"), "full")
        overview = ai_context_mode_settings_overview()
        self.assertIn("Compact — fewer", overview)
        self.assertIn("Balanced (default)", overview)
        self.assertIn("Full evidence — complete", overview)
        compact_tools = tool_names_for_context_mode("compact", "triage")
        self.assertIsNotNone(compact_tools)
        self.assertIn("detect_anomalies", compact_tools)
        self.assertIn("search_timeline", compact_tools)
        self.assertNotIn("what_if", compact_tools)
        # Start investigation / auto_investigate must expose investigate tools
        # even when the guided UI is still on idle/triage (Balanced default).
        auto_tools = tool_names_for_context_mode("balanced", "auto_investigate")
        self.assertIn("investigate", auto_tools)
        self.assertIn("correlate_events", auto_tools)
        self.assertNotIn(
            "investigate",
            tool_names_for_context_mode("balanced", "idle"),
        )
        full_tools = tool_names_for_context_mode("full", "triage")
        self.assertIsNotNone(full_tools)
        self.assertIn("detect_anomalies", full_tools)
        self.assertIn("verify_claim", full_tools)
        self.assertNotIn("what_if", full_tools)
        self.assertLess(len(full_tools), 40)
        report_tools = tool_names_for_context_mode("compact", "report")
        self.assertIn("generate_report", report_tools)
        self.assertIn("export_report", report_tools)
        self.assertNotIn("export_investigation", report_tools)
        findings = "\n".join(
            [
                "Analysis Findings",
                "",
                "1. [ERROR] id=e1 Critical stall",
                "   CS[22] blocked jump:100",
                "",
                "2. [INFO] id=i1 Idle note",
                "   Idle[0] idle",
                "",
                "3. [WARNING] id=w1 Thrash",
                "   CS[22] migrates jump:200",
                "",
                "4. [INFO] id=i2 Tick",
                "   TICK ok",
                "",
                "5. [INFO] id=i3 Load",
                "   load ok",
                "",
                "6. [INFO] id=i4 Extra",
                "   extra",
                "",
                "7. [WARNING] id=w2 Mutex",
                "   mutex jump:300",
                "",
            ]
        )
        compact = compact_findings_text(findings, "compact")
        self.assertIn("Critical stall", compact)
        self.assertIn("jump:100", compact)
        self.assertIn("Thrash", compact)
        self.assertIn("4 more finding", compact)
        self.assertNotIn("id=i4 Extra", compact)
        payload = compact_tool_result_payload(
            {"ok": True, "message": "rows", "rows": list(range(25)),
             "experiments": [{"change": f"c{i}"} for i in range(8)]},
            "compact",
        )
        self.assertEqual(len(payload["rows"]), 8)
        self.assertEqual(len(payload["experiments"]), 3)
        self.assertTrue(payload["truncated"])
        hist = compact_chat_history(
            [
                {"role": "system", "content": "sys"},
                {"role": "user", "content": "q1"},
                {"role": "assistant", "content": "a1"},
                {"role": "user", "content": "q2"},
                {"role": "assistant", "content": "a2"},
                {"role": "user", "content": "q3"},
                {"role": "assistant", "content": "a3"},
            ],
            "compact",
            investigation_summary="Focus: CS[22] stall",
        )
        users = [m["content"] for m in hist if m["role"] == "user"]
        self.assertTrue(any("Investigation summary" in u for u in users))
        self.assertIn("q2", users)
        self.assertIn("q3", users)
        self.assertNotIn("q1", users)

    def test_falsify_migration(self) -> None:
        f = falsification_checks({
            "title": "Migration thrash", "text": "CS[22] bounce",
        })
        self.assertTrue(any("migration" in x.lower() for x in f["would_disprove"]))

    def test_validator_flags_invented_task_and_out_of_window_jump(self) -> None:
        report = validate_ai_response(
            "Ghost[99] at jump:9.9 caused CS[22] stall",
            known_tasks=["CS[22]"],
            cursor_lo=1.0,
            cursor_hi=2.0,
        )
        self.assertFalse(report["ok"])
        kinds = {c["kind"] for c in report["claims"] if not c["ok"]}
        self.assertIn("task", kinds)
        self.assertIn("jump", kinds)

    def test_validator_accepts_in_scope_task(self) -> None:
        report = validate_ai_response(
            "CS[22] migrates at jump:1.5",
            known_tasks=["CS[22]"],
            cursor_lo=1.0,
            cursor_hi=2.0,
        )
        self.assertTrue(report["ok"])

    def test_interpret_and_privacy_and_capability(self) -> None:
        q = interpret_investigation_query("Why did TaskA become slow?")
        self.assertEqual(q["mode"], "diagnose")
        self.assertIn("blocking", q.get("scope") or q.get("areas") or [])
        priv = classify_trace_privacy(endpoint_is_local=True)
        self.assertEqual(priv["level"], "local")
        cap = infer_model_capability("phi4-mini:3.8b")
        self.assertIn(cap["tool_calling"], ("partial", "yes", "no", "unknown"))
        self.assertIn("Chat", format_capability_report(cap))

    def test_experiment_partial(self) -> None:
        result = validate_experiment(
            {"migrations": -70, "blocking": -10, "execution": -3},
            {"migrations": -72, "blocking": 8, "execution": -3},
        )
        self.assertEqual(result["result"], "PARTIALLY VALIDATED")

    def test_templates_and_history(self) -> None:
        tpls = builtin_investigation_templates()
        self.assertTrue(tpls)
        self.assertTrue(tpls[0].get("steps"))
        hit = match_historical_knowledge(
            "CS[22]",
            current={"migrations": 47},
            history={"CS[22]": {
                "issue": "Migration thrashing",
                "fix": "Core affinity",
                "build": "1.8.3",
                "migrations": 12,
            }},
        )
        self.assertTrue(hit.get("ok"))
        self.assertTrue(hit.get("previous_issue") or hit.get("flags"))

    def test_catalog_and_user_templates_round_trip(self) -> None:
        catalog = historical_knowledge_for_finding({
            "title": "Excessive bouncing / core thrashing",
            "text": "CS[22] migrates heavily",
        })
        self.assertEqual(catalog.get("previous_issue"), "Migration thrashing")
        prompt = investigation_mode_prompt("diagnose")
        self.assertIn("investigate", prompt)
        self.assertIn("correlate_events", prompt)
        self.assertIn("verify_claim", prompt)
        self.assertIn("challenge_conclusion", prompt)
        self.assertNotIn("Call these tools in order", prompt)
        self.assertIn("challenge_conclusion", prompt)
        report = investigation_mode_prompt("report")
        self.assertIn("generate_report", report)
        self.assertIn("export_report", report)
        self.assertIn("Call generate_report, then", report)
        self.assertNotIn("only when the user asks", report)
        tpl = new_user_investigation_template(
            "CPU Latency", ["detect_anomalies", "investigate"])
        dumped = dump_user_investigation_templates([tpl])
        parsed = parse_user_investigation_templates(dumped)
        self.assertEqual(len(parsed), 1)
        self.assertEqual(parsed[0]["label"], "CPU Latency")
        self.assertEqual(parsed[0]["steps"], ["detect_anomalies", "investigate"])
        self.assertTrue(parsed[0].get("user"))

    def test_evidence_panel_includes_quality_and_disprove(self) -> None:
        ctx = build_investigate_context(
            [{"id": "f1", "severity": "warning",
              "title": "Mutex contention",
              "text": "TASK_A[1] blocking on mutex",
              "evidence": [{"label": "blocking: stall", "time": 1.08}]}],
            "f1",
        )
        payload = extract_evidence_panel_payload("investigate", {"ok": True, **ctx})
        self.assertIsNotNone(payload)
        self.assertIn("evidence_quality", payload)
        md = format_evidence_panel_markdown(payload, "English")
        self.assertIn("Evidence Quality", md)
        self.assertIn("missing evidence", md.lower())
        self.assertIn("Confidence evolution", md)
        self.assertIn("Historical knowledge", md)
        self.assertIn("btfhyp:supported", md)
        self.assertIn("btfhyp:compare/all", md)
        self.assertIn("Supporting evidence", md)
        self.assertIn("**Status:**", md)
        self.assertIn("Investigation details", md)

    def test_scope_privacy_experiment_and_knowledge(self) -> None:
        from btf_viewer_pkg.ai_case import (
            apply_cloud_privacy,
            apply_experiment_to_hypotheses,
            experiment_percents_from_compare,
            format_coverage_count_lines,
            format_experiment_verdict,
            format_privacy_chip,
            format_quality_flag_lines,
            interpreted_run_prompt,
            new_user_historical_entry,
            parse_user_historical_knowledge,
            sanitize_annotations_text,
            should_confirm_interpreted_query,
            structured_output_from_text,
            toggle_interpreted_scope,
            tool_calling_from_chat_response,
            VALIDATE_EXPERIMENT_PROMPT,
        )
        from btf_viewer_pkg.ai_investigation import (
            format_scope_action_links,
            parse_btf_scope_href,
        )

        interpreted = {
            "interpreted_question": "Why is CS[22] slow?",
            "mode": "diagnose",
            "scope": ["execution", "blocking"],
        }
        flipped = toggle_interpreted_scope(interpreted, "migrations")
        self.assertIn("migrations", flipped["scope"])
        flipped = toggle_interpreted_scope(flipped, "execution")
        self.assertNotIn("execution", flipped["scope"])
        prompt = interpreted_run_prompt(flipped)
        self.assertIn("Why is CS[22] slow?", prompt)
        md = format_scope_action_links(flipped, {})
        self.assertIn("btfscope:run/all", md)
        self.assertEqual(parse_btf_scope_href("btfscope:toggle/priority_inheritance")[0], "toggle")

        blocked = apply_cloud_privacy("CS[22] stall", "Why CS[22]?", sensitive=True, endpoint_is_local=False)
        self.assertTrue(blocked["blocked"])
        redacted = apply_cloud_privacy(
            "CS[22] stall", "Why CS[22]?",
            endpoint_is_local=False, redact_task_names=True,
        )
        self.assertIn("Task-1", redacted["findings_text"])
        self.assertNotIn("CS[22]", redacted["findings_text"])
        cloud_notes = apply_cloud_privacy(
            'Annotation: secret note\nCS[22] stall', 'Why?',
            endpoint_is_local=False, redact_task_names=False,
        )
        self.assertIn("[annotation]", cloud_notes["findings_text"])
        self.assertNotIn("secret note", cloud_notes["findings_text"])
        self.assertTrue(should_confirm_interpreted_query("Why is CS[22] slow?"))
        self.assertFalse(should_confirm_interpreted_query(
            "Why?\n\nInterpreted as diagnose. Investigation scope: blocking.",
        ))
        self.assertFalse(should_confirm_interpreted_query(
            "Why?", already_interpreted=True,
        ))
        self.assertFalse(should_confirm_interpreted_query(
            "Why is CS[22] slow?", has_conversation=True,
        ))
        self.assertFalse(should_confirm_interpreted_query("tell me more"))
        self.assertFalse(should_confirm_interpreted_query("Continue"))
        self.assertTrue(should_confirm_interpreted_query("Why is it still slow?"))
        percents = experiment_percents_from_compare({
            "checks": [{
                "id": "migrations", "delta": -72.0, "detail": "-72.0% (threshold 20%)",
            }],
        })
        self.assertEqual(percents["migrations"], -72.0)
        self.assertIn("Use validate_experiment", VALIDATE_EXPERIMENT_PROMPT)
        self.assertIn("VALIDATED", VALIDATE_EXPERIMENT_PROMPT)
        self.assertIn("candidate", VALIDATE_EXPERIMENT_PROMPT)
        from btf_viewer_pkg.ai_investigation import compare_performance_metrics
        from btf_viewer_pkg.ai_tools import compare_performance_tabs
        tabs = compare_performance_tabs(
            {"migrations": 10, "missed_ticks": 0},
            {"migrations": 40, "missed_ticks": 0},
            label_a="after", label_b="before",
        )
        filled = experiment_percents_from_compare(tabs)
        self.assertIn("migrations", filled)
        self.assertLess(filled["migrations"], 0)
        self.assertTrue(structured_output_from_text('{"ok": true}'))
        self.assertEqual(format_privacy_chip({"level": "local"}), "🟢 Local")
        self.assertIn("[annotation]", sanitize_annotations_text("note: \"leak\""))
        qlines = format_quality_flag_lines(
            {"flags": {"direct_evidence": True, "alternative_tested": "partial"}},
            {},
        )
        self.assertTrue(any("✓" in ln for ln in qlines))
        clines = format_coverage_count_lines(
            {"directly_observed": "5/7", "timeline_verified": 4,
             "metric_verified": 6, "unverified_assumptions": 2, "claims": 7},
            {},
        )
        self.assertTrue(any("5/7" in ln for ln in clines))

        self.assertEqual(format_experiment_verdict("VALIDATED"), "Hypothesis validated")
        hyps = apply_experiment_to_hypotheses(
            [{"id": "h1", "hypothesis": "thrash", "status": "possible"}],
            {"result": "VALIDATED"},
        )
        self.assertEqual(hyps[0]["status"], "supported")
        entry = new_user_historical_entry(
            {"task": "CS[22]", "title": "Thrash", "migrations": 47},
            {"migrations": 47},
        )
        store = parse_user_historical_knowledge([entry])
        self.assertEqual(store[0]["task"], "CS[22]")
        self.assertEqual(store[0]["metrics"].get("migrations"), 47)
        self.assertTrue(tool_calling_from_chat_response({
            "choices": [{"message": {"tool_calls": [{"id": "1"}]}}],
        }))
        self.assertFalse(tool_calling_from_chat_response({
            "choices": [{"message": {"content": "PONG"}}],
        }))

    def test_investigation_template_prompt_lists_tools(self) -> None:
        from btf_viewer_pkg.ai_case import investigation_template_prompt

        tpls = builtin_investigation_templates()
        prompt = investigation_template_prompt(tpls[0])
        self.assertIn(tpls[0]["label"], prompt)
        self.assertIn(tpls[0]["steps"][0], prompt)

    def test_catalog_extracts_tasks_from_findings(self) -> None:
        cat = build_validation_catalog(findings_text="CS[22] migrates; Idle[0] idle")
        self.assertIn("CS[22]", cat["tasks"])

    def test_offline_benchmark_dataset(self) -> None:
        root = BTF_ROOT / "tests" / "ai"
        cases = load_benchmark_dataset(str(root))
        self.assertEqual(
            [c["id"] for c in cases],
            [
                "migration_thrash",
                "mutex_contention",
                "priority_inversion",
                "deadline_miss",
                "load_imbalance",
                "trace_regression",
                "explain_region",
                "adversarial_mutex_vs_starvation",
                "adversarial_exec_vs_preemption",
                "adversarial_correlation_not_cause",
                "adversarial_out_of_scope_time",
                "period_jitter",
                "waiter_owner_handoff",
                "stats_page_next_check",
                "response_vs_blocking",
                "preempt_matrix_vs_chain",
                "mutex_block_vs_wait_queue",
            ],
        )
        for case in cases:
            path = Path(case["trace_path"])
            self.assertTrue(path.is_file(), case["id"])
            text = path.read_text(encoding="utf-8")
            self.assertIn("#version", text)
            self.assertIn("#scenario", text)
        result = run_offline_benchmark(root, fail_under=50)
        self.assertTrue(result["ok"], result["report"])
        self.assertEqual(len(result["rows"]), 17)
        adv_ids = {
            "adversarial_mutex_vs_starvation",
            "adversarial_exec_vs_preemption",
            "adversarial_correlation_not_cause",
            "adversarial_out_of_scope_time",
            "period_jitter",
            "waiter_owner_handoff",
            "stats_page_next_check",
            "response_vs_blocking",
            "preempt_matrix_vs_chain",
            "mutex_block_vs_wait_queue",
        }
        self.assertEqual({r["id"] for r in result["rows"] if r["id"] in adv_ids}, adv_ids)
        for row in result["rows"]:
            if row["id"] in adv_ids:
                self.assertEqual(row.get("false_confirmation_rate"), 0, row["id"])
                self.assertEqual(row.get("false_causal_rate"), 0, row["id"])
                self.assertEqual(row.get("premature_conclusion_rate"), 0, row["id"])

    def test_adversarial_trap_response_is_penalized(self) -> None:
        expected = {
            "finding_types": ["starvation"],
            "tasks": ["Waiter[2]"],
            "root_cause_class": "starvation",
            "trap_phrases": ["mutex contention"],
            "required_tools": ["investigate"],
            "no_causal": False,
        }
        trap = score_benchmark_case(
            expected,
            actual_finding_ids=["mutex"],
            actual_tasks=["Waiter[2]"],
            actual_tools=[],
            actual_conclusion=(
                "Waiter[2] stalled from mutex contention. Confidence: High."
            ),
        )
        self.assertEqual(trap["false_confirmation_rate"], 100)
        self.assertEqual(trap["parts"]["root_cause"], 0)
        self.assertEqual(trap["premature_conclusion_rate"], 100)
        good = score_adversarial_metrics(
            expected,
            actual_conclusion="Waiter[2] CPU starvation from preemption, not mutex contention.",
            tools=["investigate"],
        )
        self.assertEqual(good["false_confirmation_rate"], 0)
        self.assertEqual(good["premature_conclusion_rate"], 0)

    def test_required_metrics_accept_statistics_page_aliases(self) -> None:
        expected = {
            "finding_types": ["jitter"],
            "tasks": ["Periodic[4]"],
            "root_cause_class": "jitter",
            "evidence": {"required_metrics": ["period / jitter", "waiter × owner", "task × core"]},
        }
        hit = score_benchmark_case(
            expected,
            actual_finding_ids=["jitter"],
            actual_tasks=["Periodic[4]"],
            actual_tools=["analyze_periodicity"],
            actual_conclusion=(
                "Periodic[4] missed a period. Open Period/Jitter, Waiter x Owner, "
                "and Task-Core. Confidence: Medium."
            ),
        )
        self.assertEqual(hit["parts"]["evidence"], 100)
        miss = score_benchmark_case(
            expected,
            actual_finding_ids=["jitter"],
            actual_tasks=["Periodic[4]"],
            actual_tools=["analyze_periodicity"],
            actual_conclusion="Periodic[4] jitter only. Confidence: Medium.",
        )
        self.assertLess(miss["parts"]["evidence"], 100)

    def test_ux_page_traps_are_penalized(self) -> None:
        tick = score_benchmark_case(
            {
                "finding_types": ["period"],
                "tasks": ["Periodic[4]"],
                "root_cause_class": "jitter",
                "trap_phrases": ["tick health"],
                "required_tools": ["analyze_periodicity"],
                "evidence": {"required_metrics": ["period / jitter"]},
            },
            actual_finding_ids=["period"],
            actual_tasks=["Periodic[4]"],
            actual_tools=[],
            actual_conclusion="Periodic[4] is a tick health problem. Confidence: High.",
        )
        self.assertEqual(tick["false_confirmation_rate"], 100)
        self.assertEqual(tick["parts"]["root_cause"], 0)
        fake_tool = score_benchmark_case(
            {
                "finding_types": ["anomalies"],
                "tasks": ["Worker[10]"],
                "root_cause_class": "tail",
                "trap_phrases": ["call detect_timeline_anomalies"],
                "required_tools": ["detect_anomalies"],
                "evidence": {"required_metrics": ["timeline anomalies"]},
            },
            actual_finding_ids=["anomalies"],
            actual_tasks=["Worker[10]"],
            actual_tools=[],
            actual_conclusion=(
                "Call detect_timeline_anomalies for Worker[10]. Confidence: High."
            ),
        )
        self.assertEqual(fake_tool["false_confirmation_rate"], 100)

    def test_benchmark_suite_xml_loads_endpoint_tls_and_env_key(self) -> None:
        import tempfile
        from unittest.mock import patch

        example = BTF_ROOT / "examples" / "ai" / "benchmark.xml"
        suite = load_benchmark_suite_xml(str(example))
        ids = [m["id"] for m in suite["models"]]
        self.assertEqual(
            ids,
            ["qwen3.5:9b", "qwen3.8:27b",
             "gemini-3.7-flash", "gemini-3.5-flash-lite"],
        )
        local = next(m for m in suite["models"] if m["base_url"].startswith("http://"))
        self.assertFalse(local["tls_verify"])
        self.assertTrue(local["base_url"])
        gemini_ids = [
            m["id"] for m in suite["models"] if m.get("api_key_env") == "GEMINI_API_KEY"
        ]
        self.assertEqual(
            gemini_ids, ["gemini-3.7-flash", "gemini-3.5-flash-lite"])
        self.assertFalse(any(m.get("optional") for m in suite["models"]))
        default_ids = [m["id"] for m in select_benchmark_suite_models(suite, "")]
        self.assertEqual(default_ids, ids)
        cloud = next(m for m in suite["models"] if m.get("api_key_env") == "GEMINI_API_KEY")
        self.assertEqual(cloud["api_key_env"], "GEMINI_API_KEY")
        self.assertTrue(cloud["tls_verify"])
        picked = select_benchmark_suite_models(suite, local["id"])
        self.assertEqual([m["id"] for m in picked], [local["id"]])
        self.assertEqual(parse_live_benchmark_models(local["id"]), [local["id"]])

        xml = """<?xml version="1.0" encoding="UTF-8"?>
<ai-benchmark>
  <dataset>tests/ai</dataset>
  <endpoint>
    <base-url>https://gateway.example:8443/v1</base-url>
    <tls-verify>false</tls-verify>
    <api-key env="BENCH_TEST_KEY">xml-fallback-key</api-key>
  </endpoint>
  <models>
    <model id="lab-model"/>
    <model id="optional-cloud" optional="true">
      <base-url>https://api.example.com/v1</base-url>
      <api-key env="BENCH_OPTIONAL_KEY"/>
    </model>
  </models>
</ai-benchmark>
"""
        with tempfile.NamedTemporaryFile("w", suffix=".xml", delete=False) as fh:
            fh.write(xml)
            tmp = fh.name
        try:
            with patch.dict(os.environ, {"BENCH_TEST_KEY": "from-env"}, clear=False):
                env_suite = load_benchmark_suite_xml(tmp)
            self.assertEqual(env_suite["models"][0]["api_key"], "from-env")
            with patch.dict(
                os.environ,
                {
                    "BENCH_TEST_KEY": "",
                    "BENCH_OPTIONAL_KEY": "",
                    "GEMINI_API_KEY": "sk-gemini-must-not-fill-optional",
                },
                clear=False,
            ):
                xml_suite = load_benchmark_suite_xml(tmp)
            self.assertEqual(xml_suite["models"][0]["api_key"], "xml-fallback-key")
            self.assertFalse(xml_suite["models"][0]["tls_verify"])
            self.assertEqual(xml_suite["models"][1]["api_key"], "")
            skipped = select_benchmark_suite_models(xml_suite, "")
            self.assertEqual([m["id"] for m in skipped], ["lab-model"])
            forced = select_benchmark_suite_models(xml_suite, "optional-cloud")
            self.assertEqual([m["id"] for m in forced], ["optional-cloud"])
        finally:
            os.unlink(tmp)

    def test_live_benchmark_injected_complete(self) -> None:
        root = BTF_ROOT / "tests" / "ai"
        cases = {c["id"]: c for c in load_benchmark_dataset(str(root))}
        suite = load_benchmark_suite_xml(
            str(BTF_ROOT / "examples" / "ai" / "benchmark.xml"))
        model = suite["models"][0]["id"]
        self.assertEqual(
            benchmark_model_category("gemini-3.7-flash"),
            "Cloud",
        )
        self.assertEqual(
            benchmark_model_category("models/gemini-3.5-flash-lite"),
            "Cloud / fast",
        )
        self.assertEqual(benchmark_model_category("claude-sonnet-5"), "Cloud")
        self.assertEqual(benchmark_model_category("kimi-k3"), "Cloud")
        ctx = benchmark_prompt_context(cases["migration_thrash"])
        self.assertIn("CS[22]", ctx)
        self.assertNotIn("finding_types", ctx)

        def complete(_query, findings, used_model, case):
            self.assertEqual(used_model, model)
            self.assertIn("Known tasks", findings)
            canned = cases[case["id"]]
            return {
                "content": canned["response"],
                "tool_calls": [{"name": n} for n in canned.get("tools") or []],
                "elapsed_s": 0.1,
            }

        live = run_live_benchmark(
            root, [model], complete=complete, fail_under=50,
        )
        self.assertTrue(live["ok"], live["report"])
        self.assertEqual(live["models"][0]["model"], model)
        offline = run_offline_benchmark(root, fail_under=50)
        self.assertEqual(
            [r["overall"] for r in live["models"][0]["rows"]],
            [r["overall"] for r in offline["rows"]],
        )
        md = format_benchmark_markdown(
            offline=offline, live=live, dataset="tests/ai",
        )
        self.assertIn(model, md)
        self.assertIn("Offline fixture scorer", md)
        self.assertIn("Live models", md)

        def empty_complete(_q, _f, _m, _c):
            return {"content": "no catalog names", "tool_calls": [], "elapsed_s": 0.01}

        weak = run_live_benchmark(
            root, [model], complete=empty_complete, fail_under=70,
        )
        self.assertFalse(weak["ok"])

    def test_parse_benchmark_context_modes(self) -> None:
        self.assertEqual(
            parse_benchmark_context_modes("all"),
            ["compact", "balanced", "full"],
        )
        self.assertEqual(parse_benchmark_context_modes("compact"), ["compact"])
        self.assertEqual(
            parse_benchmark_context_modes("compact,balanced"),
            ["compact", "balanced"],
        )

    def test_live_benchmark_compare_context_modes(self) -> None:
        root = BTF_ROOT / "tests" / "ai"
        cases = {c["id"]: c for c in load_benchmark_dataset(str(root))}
        model = "fixture-model"

        def complete(_query, _findings, used_model, case, context_mode="full"):
            self.assertEqual(used_model, model)
            canned = cases[case["id"]]
            tok = {"compact": 900, "balanced": 1800, "full": 3200}[context_mode]
            return {
                "content": canned["response"],
                "tool_calls": [{"name": n} for n in canned.get("tools") or []],
                "elapsed_s": {"compact": 1.0, "balanced": 2.0, "full": 3.0}[context_mode],
                "usage": {
                    "prompt_tokens": tok - 100,
                    "completion_tokens": 100,
                    "total_tokens": tok,
                },
            }

        live = run_live_benchmark(
            root,
            [model],
            complete=complete,
            fail_under=50,
            context_modes=["compact", "balanced", "full"],
        )
        self.assertEqual(live["context_modes"], ["compact", "balanced", "full"])
        self.assertEqual(len(live["models"]), 3)
        by_mode = {b["context_mode"]: b for b in live["models"]}
        self.assertEqual(by_mode["compact"]["rows"][0]["total_tokens"], 900)
        self.assertEqual(by_mode["full"]["rows"][0]["total_tokens"], 3200)
        md = format_benchmark_markdown(live=live, dataset="tests/ai")
        self.assertIn("Context mode comparison", md)
        self.assertIn("Compact", md)
        self.assertIn("Total tok", md)

    def test_live_benchmark_report_marks_error_rows_not_fail(self) -> None:
        """A case that raised (API error) must print ERROR, not FAIL — matches
        the AI_BENCHMARK.md table's ``ERROR`` flag (see format_benchmark_markdown)."""
        root = BTF_ROOT / "tests" / "ai"
        cases = {c["id"]: c for c in load_benchmark_dataset(str(root))}
        model = "fixture-model"
        boom_id = next(iter(cases))

        def complete(_query, _findings, _used_model, case, context_mode="full"):
            if case["id"] == boom_id:
                raise RuntimeError(
                    "HTTP 503: This model is currently experiencing high demand.")
            canned = cases[case["id"]]
            return {
                "content": canned["response"],
                "tool_calls": [{"name": n} for n in canned.get("tools") or []],
                "elapsed_s": 0.1,
            }

        live = run_live_benchmark(root, [model], complete=complete, fail_under=50)
        block = live["models"][0]
        boom_row = next(r for r in block["rows"] if r["id"] == boom_id)
        self.assertTrue(boom_row.get("error"))
        self.assertFalse(boom_row.get("pass"))
        self.assertIn(f"  {boom_id:24}", block["report"])
        boom_line = next(
            line for line in block["report"].splitlines()
            if line.strip().startswith(boom_id)
        )
        self.assertIn("ERROR", boom_line)
        self.assertNotIn("FAIL", boom_line)

        md = format_benchmark_markdown(live=live, dataset="tests/ai")
        self.assertIn(f"| {boom_id} |", md)
        md_line = next(
            line for line in md.splitlines() if line.startswith(f"| {boom_id} |"))
        self.assertTrue(md_line.rstrip().endswith("ERROR |"))

    def test_cli_ai_test_runs_dataset(self) -> None:
        from btf_viewer_pkg.cli import _cli_ai_test_run
        from argparse import Namespace

        path = str(BTF_ROOT / "tests" / "ai")
        rc = _cli_ai_test_run(Namespace(dataset=path, fail_under=50))
        self.assertEqual(rc, 0)

    def test_select_benchmark_cases_filters_by_only_cases(self) -> None:
        """``--only-cases`` narrows the dataset the same way ``--models`` narrows
        the suite XML: empty keeps everything, known ids filter in order given,
        and an unknown id raises so a typo doesn't silently score zero cases."""
        cases = load_benchmark_dataset(str(BTF_ROOT / "tests" / "ai"))
        all_ids = [c["id"] for c in cases]
        self.assertGreater(len(all_ids), 1)

        self.assertEqual(
            [c["id"] for c in select_benchmark_cases(cases, "")], all_ids)

        one_id = all_ids[-1]
        two_id = all_ids[0]
        picked = select_benchmark_cases(cases, f" {one_id} , {two_id} ")
        self.assertEqual([c["id"] for c in picked], [one_id, two_id])

        with self.assertRaises(ValueError) as ctx:
            select_benchmark_cases(cases, "not-a-real-case")
        self.assertIn("not-a-real-case", str(ctx.exception))

    def test_parse_benchmark_markdown_round_trips_offline_and_live(self) -> None:
        """merge_benchmark_report needs to recover enough from a prior
        AI_BENCHMARK.md to regenerate byte-identical tables/aggregates for
        blocks that were not rerun — verify the round trip is lossless for a
        multi-context-mode live run plus the offline scorer."""
        root = BTF_ROOT / "tests" / "ai"
        offline = run_offline_benchmark(root, fail_under=50)

        def complete(_query, _findings, _used_model, case, context_mode="full"):
            return {
                "content": case.get("response") or "",
                "tool_calls": [{"name": n} for n in case.get("tools") or []],
                "elapsed_s": 1.5,
                "usage": {
                    "prompt_tokens": 100, "completion_tokens": 20, "total_tokens": 120,
                },
            }

        live = run_live_benchmark(
            root, ["fixture-model"], complete=complete, fail_under=50,
            context_modes=["compact", "full"])
        md = format_benchmark_markdown(offline=offline, live=live, dataset="tests/ai")
        parsed = parse_benchmark_markdown(md)
        self.assertIn("offline", parsed)
        self.assertIn("live", parsed)
        re_md = format_benchmark_markdown(
            offline=parsed["offline"], live=parsed["live"], dataset="tests/ai")
        self.assertEqual(md, re_md)

    def test_parse_benchmark_markdown_round_trips_error_rows(self) -> None:
        root = BTF_ROOT / "tests" / "ai"
        cases = {c["id"]: c for c in load_benchmark_dataset(str(root))}
        boom_id = next(iter(cases))

        def complete(_query, _findings, _used_model, case, context_mode="full"):
            if case["id"] == boom_id:
                raise RuntimeError("HTTP 503: high demand, try again later.")
            return {"content": case.get("response") or "", "elapsed_s": 1.0}

        live = run_live_benchmark(root, ["m"], complete=complete, fail_under=50)
        md = format_benchmark_markdown(live=live, dataset="tests/ai")
        parsed = parse_benchmark_markdown(md)
        re_md = format_benchmark_markdown(live=parsed["live"], dataset="tests/ai")
        self.assertEqual(md, re_md)

    def test_merge_benchmark_report_preserves_untouched_blocks(self) -> None:
        """Rerunning just one model/context (e.g. gemini-3.7-flash in Full
        evidence) must update only that block — every other model, context
        mode, and offline case already in AI_BENCHMARK.md stays untouched."""
        root = BTF_ROOT / "tests" / "ai"
        offline = run_offline_benchmark(root, fail_under=50)

        def complete_v1(_q, _f, model, case, context_mode="full"):
            return {"content": case.get("response") or "", "elapsed_s": 1.0}

        first_live = run_live_benchmark(
            root, ["model-a", "model-b"], complete=complete_v1, fail_under=50,
            context_modes=["compact", "full"])
        original_md = format_benchmark_markdown(
            offline=offline, live=first_live, dataset="tests/ai")

        def complete_v2(_q, _f, model, case, context_mode="full"):
            return {"content": "totally different reply", "elapsed_s": 9.9}

        rerun_live = run_live_benchmark(
            root, ["model-a"], complete=complete_v2, fail_under=0,
            context_modes=["full"])
        merged_offline, merged_live = merge_benchmark_report(
            original_md, offline=None, live=rerun_live)
        # No fresh offline run this time — the prior offline table (untouched)
        # is still recovered from original_md so it isn't dropped from the file.
        self.assertEqual(
            [r["id"] for r in merged_offline["rows"]],
            [r["id"] for r in offline["rows"]],
        )
        merged_md = format_benchmark_markdown(
            offline=merged_offline, live=merged_live, dataset="tests/ai")
        self.assertIn("## Offline fixture scorer", merged_md)

        # model-b (untouched) keeps every one of its original blocks verbatim.
        for mode_label in ("Compact", "Full evidence"):
            marker = f"### `model-b` — {mode_label}"
            self.assertIn(marker, original_md)
            self.assertIn(marker, merged_md)
        b_compact_old = original_md.split("### `model-b` — Compact")[1].split("### `")[0]
        b_compact_new = merged_md.split("### `model-b` — Compact")[1].split("### `")[0]
        self.assertEqual(b_compact_old, b_compact_new)

        # model-a Compact (untouched by the rerun) is also preserved verbatim.
        a_compact_old = original_md.split("### `model-a` — Compact")[1].split("### `")[0]
        a_compact_new = merged_md.split("### `model-a` — Compact")[1].split("### `")[0]
        self.assertEqual(a_compact_old, a_compact_new)

        # model-a Full evidence (rerun) reflects the new response.
        a_full_new = merged_md.split("### `model-a` — Full evidence")[1].split("### `")[0]
        self.assertIn("Mean latency: **9.9s**", a_full_new)
        self.assertNotIn("Mean latency: **1.0s**", a_full_new)

    def test_cli_ai_test_only_cases_narrows_offline_report(self) -> None:
        from btf_viewer_pkg.cli import _cli_ai_test_run
        from argparse import Namespace

        path = str(BTF_ROOT / "tests" / "ai")
        cases = load_benchmark_dataset(path)
        case_id = cases[0]["id"]
        rc = _cli_ai_test_run(
            Namespace(dataset=path, fail_under=50, only_cases=case_id))
        self.assertEqual(rc, 0)

        rc = _cli_ai_test_run(
            Namespace(dataset=path, fail_under=50, only_cases="not-a-real-case"))
        self.assertEqual(rc, 1)

    def test_cli_ai_test_output_merges_with_existing_report(self) -> None:
        """Writing -o over an existing AI_BENCHMARK.md-style report merges in
        the new (possibly --only-cases-restricted) run instead of dropping
        every case that wasn't rerun this time; --replace-report opts out."""
        import tempfile
        from btf_viewer_pkg.cli import _cli_ai_test_run
        from argparse import Namespace

        path = str(BTF_ROOT / "tests" / "ai")
        all_ids = [c["id"] for c in load_benchmark_dataset(path)]
        self.assertGreater(len(all_ids), 1)
        with tempfile.TemporaryDirectory() as tmp:
            out = os.path.join(tmp, "AI_BENCHMARK.md")
            rc = _cli_ai_test_run(Namespace(dataset=path, fail_under=50, output=out))
            self.assertEqual(rc, 0)
            full_text = Path(out).read_text(encoding="utf-8")
            for cid in all_ids:
                self.assertIn(f"| {cid} |", full_text)

            one_id = all_ids[0]
            rc = _cli_ai_test_run(Namespace(
                dataset=path, fail_under=50, output=out, only_cases=one_id))
            self.assertEqual(rc, 0)
            merged_text = Path(out).read_text(encoding="utf-8")
            for cid in all_ids:
                self.assertIn(f"| {cid} |", merged_text)

            rc = _cli_ai_test_run(Namespace(
                dataset=path, fail_under=50, output=out, only_cases=one_id,
                replace_report=True))
            self.assertEqual(rc, 0)
            replaced_text = Path(out).read_text(encoding="utf-8")
            self.assertIn(f"| {one_id} |", replaced_text)
            other_id = next(cid for cid in all_ids if cid != one_id)
            self.assertNotIn(f"| {other_id} |", replaced_text)

    def test_run_live_benchmark_only_cases_scores_subset(self) -> None:
        root = BTF_ROOT / "tests" / "ai"
        all_cases = load_benchmark_dataset(str(root))
        case_id = all_cases[0]["id"]
        model = "fixture-model"

        def complete(_query, _findings, _used_model, case, context_mode="full"):
            return {"content": case.get("response") or "", "tool_calls": []}

        live = run_live_benchmark(
            root, [model], complete=complete, fail_under=0, case_ids=case_id)
        rows = live["models"][0]["rows"]
        self.assertEqual([r["id"] for r in rows], [case_id])


class InvestigationCaseParitySurfaceTests(unittest.TestCase):
    def test_js_exports_match_python_helpers(self) -> None:
        js = (BTF_ROOT / "web/src/utils/aiCase.js").read_text(encoding="utf-8")
        for name in (
            "buildInvestigationCase",
            "validateAiResponse",
            "evidenceQualityFromScore",
            "inferModelCapability",
            "classifyTracePrivacy",
            "classifyPrivacy",
            "interpretQuestion",
            "scoreBenchmarkCase",
            "runOfflineBenchmark",
            "formatPrivacyChip",
            "investigationTemplatePrompt",
            "investigationModePrompt",
            "parseUserInvestigationTemplates",
            "dumpUserInvestigationTemplates",
            "historicalKnowledgeForFinding",
            "statusWithCost",
            "formatCostStatus",
            "formatContextUsageStatus",
            "normalizeAiContextMode",
            "compactFindingsText",
            "compactChatHistory",
            "toolNamesForContextMode",
            "clampAiSplitBottom",
            "scoreAdversarialMetrics",
            "costMeterActive",
            "applyCloudPrivacy",
            "toggleInterpretedScope",
            "interpretedRunPrompt",
            "formatExperimentVerdict",
            "applyExperimentToHypotheses",
            "parseUserHistoricalKnowledge",
            "toolCallingFromChatResponse",
            "shouldConfirmInterpretedQuery",
            "looksLikeFollowupAsk",
            "experimentPercentsFromCompare",
            "VALIDATE_EXPERIMENT_PROMPT",
            "sanitizeAnnotationsText",
            "formatQualityFlagLines",
            "mergeLiveCapability",
            "INVESTIGATION_SCOPE_OPTIONS",
            "investigationGuideStage",
            "investigationIssueCard",
            "formatInvestigationIssueCard",
            "dumpInvestigationSession",
            "parseInvestigationSession",
            "investigationSessionHasChat",
            "GUIDED_STAGES",
            "ESTIMATE_BANNER",
            "guideStageNeedles",
        ):
            self.assertIn(name, js, name)


if __name__ == "__main__":
    unittest.main()
