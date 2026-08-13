<a id="ai-assistant-guide" name="ai-assistant-guide">&#x200B;</a>
# AI Assistant ![](../images/readme/h1.svg)

Setup, tools, diagrams, Desktop vs Web, troubleshooting, CLI details, and **workflows / use cases** for the BTF Viewer **AI** tab.

For day-to-day panel usage (templates, Apply/Skip, Analysis dialog buttons), see the [user guide → AI Assistant](README.md#ai-assistant). Ask-order playbooks: [WORKFLOWS.md §7](WORKFLOWS.md#7-ai-assistant-flow). End-to-end flows and symptom → tool tables: [Workflows and use cases](#workflows-and-use-cases).

Heading level: ![](../images/readme/h2.svg) section · ![](../images/readme/h3.svg) subsection · ![](../images/readme/h4.svg) topic · ![](../images/readme/h5.svg) detail


---

<a id="contents" name="contents">&#x200B;</a>
## Contents ![](../images/readme/h2.svg)

| Section | |
|---------|--|
| [How it works](#how-it-works) | Context, evidence, investigation plan |
| [Investigation Case](#investigation-case) | Case model, hypotheses, evidence graph, validator |
| [Workflows and use cases](#workflows-and-use-cases) | End-to-end, verify / explain / auto, symptom → tools |
| [Endpoints and models](#endpoints-and-models) | Ollama / cloud, context size, local models |
| [AI capability / model matrix](#capability-matrix) | Local 3B vs 7B+ vs cloud, which model to pick |
| [GUI tools](#gui-tools) | Tool schema and Apply / Undo |
| [Diagrams](#diagrams) | Mermaid and tables in replies |
| [Desktop vs web](#desktop-vs-web) | Parity matrix |
| [Troubleshooting](#troubleshooting) | CORS, auth, TLS, timeouts |
| [Opening the web app from `file://`](#opening-the-web-app-from-file) | Ollama CORS for disk pages |
| [CLI regression gate](#cli-regression-gate) | Headless `analyze` / `ai-test` |

---

<a id="how-it-works" name="how-it-works">&#x200B;</a>
## How it works ![](../images/readme/h2.svg)

The **AI** tab answers diagnostic questions using structured **Analysis Findings** and summary metrics—not the raw `.btf` event stream. That keeps the prompt compact (token-efficient) and analysis fast. The Trace Compare template sends those tables instead of Findings.

When a question needs granular per-task time-series, the model can call `query_raw_metric` to pull a scoped series on demand (still never the raw BTF file). `search_timeline` locates STI / tag / task timestamps like Find. `trigger_compare` returns Trace Compare CSV when two tabs are open. `detect_anomalies` ranks Findings as Critical / Warning / Info. `correlate_events` merges blocking / execution / migration / sync / priority events for one task. `find_critical_path` walks preempt/block/mutex around a timestamp. `compare_performance` returns structured A vs B deltas (two tabs). `regression_explain` narrates the primary A vs B change. `investigate` builds a root-cause chain plus hypotheses and suggested tools. `generate_report` returns typed engineering markdown (then `export_report` to save). `check_budget` compares WCET/response/deadline budgets; `optimize` returns qualitative mitigations; `what_if` runs a heuristic slice-replay simulator; `optimize_experiment` ranks automatic candidates; `analyze_traces` ranks all open tabs; `baseline_score` flags drift vs a stored baseline; `recommend_experiments` suggests bench follow-ups; `detect_priority_inversion` / `find_related_findings` / `compare_tasks` cover PI suspects, adjacent findings, and two-task deltas; `explain_finding` / `interpret_query` / `validate_experiment` / `manage_hypotheses` cover levelled explanations, query interpretation, experiment close-out, and hypothesis status; `bookmark_finding` pins semantic investigation marks; `investigation_replay` summarises a completed investigation. Query-only batches (the read-only tools in [GUI tools](#gui-tools)) run immediately; mixed GUI batches wait for **Apply** unless **Auto-apply GUI actions** is on. Export tools (`export_report`, `export_investigation`) still show a save dialog.

Important conclusions should cite evidence (`jump:TIME`, metric names) and state **confidence** (High / Medium / Low) plus evidence quality (Directly observed / Strong correlation / Possible explanation / Insufficient evidence). The system prompt asks the model not to invent numbers, task names, or `jump:TIME` values absent from findings, tool results, or Trace Compare tables — and, when a **Cursor region window** is listed, to cite only times inside that window.

**Investigate / Root cause / Verify finding / Auto investigate / What-if / Optimize / Diagnostic report** show an **Investigation plan** checklist in the AI panel (steps advance as tools run; the final text reply marks remaining steps done). Analysis Findings may include anomaly rows (WCET Max≫Avg spikes, extreme migration bursts). **Explain finding** (Analysis **Explain…**: Quick / Technical / Deep) calls `explain_finding` with `level=`. Mode chips and **More → Investigations** (including **Save as template…**) start tool sequences without adding templates after Auto investigate. Evidence hypothesis rows offer Support / Reject / Need evidence / Test / Compare.

Right-click a timeline segment → **Ask AI about this event** to ask about that exact task/segment (`Explain the timeline event for task … around jump:TIME`), same as Explain region but scoped to one segment. With **≥2 cursors**, the timeline context menu also offers **Explain this region with AI** (`explain_region`); the AI panel **Explain region** template is always available — without two cursors it runs on full-trace Findings (no region window). When cursors are placed, the prompt includes an explicit **Cursor region window** (`jump:lo … jump:hi`) so replies should stay in-window. When `investigate` returns a root-cause chain and hypotheses, the Evidence panel renders a small **Investigation tree** plus an **Evidence Quality** meter (Strong / Medium-High / Medium / Weak — a diagnostic heuristic, **not** a probability). Direct evidence times, timeline correlation, and metric checks raise the band; untested alternatives lower it. The panel also lists **what would disprove** the conclusion, **evidence coverage**, and an **evidence graph** (finding → evidence → hypotheses). After the final reply, a host-side **validator** flags invented task names and `jump:TIME` values outside the cursor window.

Natural-language timeline questions (e.g. “find STI wait around TaskA”) are answered via **`search_timeline`** — no separate search UI.

Recommended ask order ([WORKFLOWS.md §7](WORKFLOWS.md#7-ai-assistant-flow)): triage overall findings → **Investigate** / **Root cause** when you want tool-driven drill-down → named metric templates → mitigations after the timeline agrees. Prefer the built-in templates; they already name the metrics and units. Concrete flows and use cases are below.

---

<a id="investigation-case" name="investigation-case">&#x200B;</a>
## Investigation Case ![](../images/readme/h2.svg)

Desktop and Web share one **Investigation Case** model (`btf-investigation-case`): question, scope (trace / C1–Cn / tasks / cores), hypotheses with status (**supported** / **possible** / **need evidence** / **rejected**), evidence graph, coverage, falsification checks, conclusion, and validation.

After each final assistant reply a host-side **validator** extracts `jump:TIME` and `Task[id]` claims and flags invented names or timestamps outside the cursor window. **Test connection** appends a heuristic **model capability** card (chat / tools / chaining). Headless eval:

```bash
make -C BTFViewer ai-test
# or: python builds/btf_viewer.py ai-test --dataset tests/ai --fail-under 70
```

Modes (Quick / Diagnose / Compare / Optimize / Report) map onto existing templates; they do not add new tools. Always confirm on the timeline.

---

<a id="workflows-and-use-cases" name="workflows-and-use-cases">&#x200B;</a>
## Workflows and use cases ![](../images/readme/h2.svg)

Same flow on **Desktop** and **Web**. Panel chrome: [README → AI Assistant](README.md#ai-assistant). Ladder and ask-order tables: [WORKFLOWS.md §7](WORKFLOWS.md#7-ai-assistant-flow).

| In this section | |
|-----------------|--|
| [End-to-end flow](#end-to-end-flow) | Load → Findings → AI → verify on timeline |
| [Investigation workflow](#investigation-workflow) | Triage → Investigate / Auto / Verify → evidence |
| [Explain region and Ask event](#explain-region-and-ask-event) | C1–Cn window and segment context menus |
| [What-if and optimize](#what-if-and-optimize-workflow) | Heuristic slice-replay (not FreeRTOS) |
| [Use cases](#use-cases) | Symptom → template / tools |
| [Worked examples](#worked-examples) | Thrash, contention, regression, region, PI |
| [Simulator limits](#simulator-limits) | What `what_if` does and does not do |

<a id="end-to-end-flow" name="end-to-end-flow">&#x200B;</a>
### End-to-end flow ![](../images/readme/h3.svg)

```text
① Load trace → Statistics (optional cursors + Limit to C1–Cn)
② Toolbar Analysis → Findings for that scope
③ AI entry (pick one):
     • Triage / Investigate / Root cause / Auto investigate…
     • Verify with AI… (selected finding)
     • Explain this region with AI (≥2 cursors) or Explain region template
     • Ask AI about this event (segment)
④ Apply GUI cards → click jump:TIME → Evidence / Reasoning (score + tree)
⑤ Confirm on timeline + named Statistics sections
⑥ What-if / Optimize / recommend_experiments  →  only after the cause matches
⑦ Diagnostic report / export_report / export_investigation  →  or CLI analyze
```

Do not ask for mitigations before the timeline agrees with the finding. Empty or mis-scoped Statistics produce confident nonsense. Prefer built-in templates: they already name metrics and units.

<a id="investigation-workflow" name="investigation-workflow">&#x200B;</a>
### Investigation workflow ![](../images/readme/h3.svg)

| Step | Template or tool | Why |
|------|------------------|-----|
| 1 | **Triage findings** / `detect_anomalies` | Rank Critical / Warning / Info |
| 2 | **Investigate** / `investigate` — or Findings **Auto investigate…** | Root-cause chain, hypotheses, alternatives, suggested tools |
| 3 | **Verify finding** / Findings **Verify with AI…** | Confirmed / Rejected / Inconclusive with jump:TIME evidence |
| 4 | `correlate_events` + `query_raw_metric` | Merge blocking / execution / migrations / sync / PI for one task |
| 5 | `find_critical_path` / `detect_priority_inversion` | Preempt/block path; L/M/H inversion suspects |
| 6 | `find_related_findings` / `compare_tasks` | Adjacent findings; side-by-side task deltas |
| 7 | `set_cursors` / `zoom_to_range` / `highlight_task` / `bookmark_finding` | Narrow the timeline (Apply unless auto-apply is on) |
| 8 | Evidence panel | Investigation tree + **Evidence Quality** + what would disprove this |
| 9 | `investigation_replay` / `generate_report` / `export_investigation` | Structured close-out; optional `export_report` |

**Root cause** walks deadline/WCET → preemption → blocking → mutex → inheritance → migration for the top finding. Use it when triage already named a suspect task.

**Auto investigate** chains verify-style steps for one finding (investigate → correlate → critical path / PI as needed) and advances the Investigation plan checklist. Use **Verify** when you already have a finding id and want a short verdict.

<a id="explain-region-and-ask-event" name="explain-region-and-ask-event">&#x200B;</a>
### Explain region and Ask event ![](../images/readme/h3.svg)

| Entry | When it appears | Scope |
|-------|-----------------|-------|
| Timeline → **Explain this region with AI** | Only with **≥2 cursors** | C1–Cn; prompt gets `Cursor region window: jump:lo … jump:hi` |
| AI panel → **Explain region** | Always | Same window when ≥2 cursors; **full-trace Findings** if none |
| Timeline segment → **Ask AI about this event** | Segment under the pointer | One task / core / segment around `jump:TIME` |

Stay inside the stated window: every `jump:TIME` in the reply should fall between C1 and Cn (or the model should say the window has no matching evidence). Enable **Limit to C1–Cn** so Statistics / Findings / `query_raw_metric` match that window. Clicking a `jump:TIME` outside the cursors usually means the model invented or reused a full-trace time — discard it and re-ask with cursors + scoped Findings.

<a id="what-if-and-optimize-workflow" name="what-if-and-optimize-workflow">&#x200B;</a>
### What-if and optimize workflow ![](../images/readme/h3.svg)

`what_if` and `optimize_experiment` are **heuristic slice-replay** tools: they reallocate measured execution slices, scale migrations / blocking, and adjust core-util balance. They are **not** a FreeRTOS kernel or deterministic scheduler. Every result carries a disclaimer. After a promising estimate, `recommend_experiments` suggests validation steps (simulation / firmware / measurement).

| Goal | What to run | Typical change phrases |
|------|-------------|------------------------|
| One concrete idea | **What-if** → `what_if` | `pin CS[28] to Core_0`, `raise priority of Low[266]`, `reduce mutex contention 50%` |
| Rank several ideas | **Optimize** → `optimize_experiment` (then optional `optimize` for qualitative notes) | Host picks pin-to-dominant / quiet core, contention −50%, priority up, migrations −50% |
| Soft advice only | `optimize` | Finding-text mitigations without scored experiments |
| What to try next on the bench | `recommend_experiments` | Validation experiments from findings heuristics |

**Reading the payload:** compare `baseline` vs `simulated` (migrations, blocking_ns, load_balance_score) and the `deltas.cost` ranking. Lower cost is better in the experiment list. Treat Medium confidence as “worth trying on the bench”; Low means the phrase was vague or slices were thin.

<a id="use-cases" name="use-cases">&#x200B;</a>
### Use cases ![](../images/readme/h3.svg)

| Situation | Before you ask | Template / tools | Then verify |
|-----------|----------------|------------------|-------------|
| Unknown — first look | Full-trace or cursor-scoped Findings | **Triage findings** → **Investigate** | Named Statistics sections; `jump:TIME` |
| Hottest / noisiest task | Findings name a suspect | **Task profile** | Execution / Blocking / Migrations |
| Tick jitter / missed ticks | Trace Health in scope | **Tick health** | Tick Distribution |
| Confirm one finding | Select it in Analysis Findings | **Verify with AI…** / **Verify finding** | Evidence panel; timeline |
| Explain a time window | ≥2 cursors; **Limit to C1–Cn** on | Context menu or **Explain region** | Only `jump:TIME` inside C1–Cn |
| One segment / ISR slice | Right-click the segment | **Ask AI about this event** | That task’s row; nearby STI |
| Auto walk a finding | Select finding → **Auto investigate…** | `auto_investigate` | Investigation plan + Evidence |
| Migration thrash / ping-pong | Scope thrash window; Findings mention the task | **Migration thrash** → `correlate_events` → **What-if** pin / **Optimize** | Migrations Rate/Ping; Heatmap / Chord; Core Affinity |
| Priority inversion / PI boost | Inheritance finding or PI episodes in scope | **Priority inversion** / `detect_priority_inversion` → `find_critical_path` | Priority Inheritance; Mutex hold |
| High blocking / mutex wait | Scope the stall; suspect task known | **Highest latency** → `query_raw_metric` blocking/sync → **What-if** contention / priority | Blocking Max; Mutex hold; Priority Inheritance |
| WCET / deadline pressure | Thresholds set in Display → Analysis | **WCET / hot CPU** or **Deadline / budget** → `check_budget` | Execution Max jump; Deadlines section |
| Compare two tasks | Both names known | `compare_tasks` | Execution / Blocking / Migrations side-by-side |
| Related findings | One finding selected | `find_related_findings` | Shared task / metric / nearby times |
| Load imbalance across cores | Multi-core util in Findings | **Core balance** → `analyze_traces` (multi-tab) or **What-if** pin to quiet core | Load Balance Score; Concurrent Active; Core Time Breakdown |
| A vs B build regression | Two tabs open | **Trace Compare** → `compare_performance` / `regression_explain` | Trace Compare pages; same scope on both builds |
| Drift vs saved baseline | Baseline profile stored (rc / localStorage) | `baseline_score` | Flags `\|z\|>2`; re-capture if needed |
| Rank all open traces | ≥2 loaded tabs | `analyze_traces` | Best tab vs Migrations / LB / missed ticks |
| Write-up for a review | Cause already confirmed | **Diagnostic report** → `generate_report` → `export_report` / `export_investigation` | Saved HTML/CSV/JSON; evidence times bookmarked |
| CI gate vs baseline | Desktop CLI | [`analyze`](#cli-regression-gate) `--fail-on-regression` (optional `--ai`) | Exit code + markdown narrative |

<a id="worked-examples" name="worked-examples">&#x200B;</a>
### Worked examples ![](../images/readme/h3.svg)

<a id="example-pin-after-thrash" name="example-pin-after-thrash">&#x200B;</a>
#### Migration thrash → pin affinity ![](../images/readme/h4.svg)

1. Place cursors on the thrash window; enable **Limit to C1–Cn**; re-open Analysis.
2. Run **Migration thrash** or **Investigate** until the hot task (e.g. `CS[22]`) and cores match the heatmap.
3. Ask **What-if**: *pin CS[22] to its dominant core* (or run **Optimize** for ranked candidates).
4. Read Δmigrations / Δload_balance_score. If migrations drop but LB worsens sharply, try pin-to-quietest via `optimize_experiment` and compare ranks.
5. On firmware: set affinity / reduce bounce; re-capture a `.btf` and **Trace Compare** the before/after tabs.

<a id="example-contention-what-if" name="example-contention-what-if">&#x200B;</a>
#### Mutex contention → shorter critical section ![](../images/readme/h4.svg)

1. **Highest latency** / `correlate_events` for the waiter; confirm hold episodes in Mutex / Priority Inheritance.
2. **What-if**: *reduce mutex contention 50% for TASK* (or another %).
3. Expect lower `blocking_ns` in the simulated payload — still an estimate. Confirm by shortening the hold in code and re-tracing.

<a id="example-regression-tabs" name="example-regression-tabs">&#x200B;</a>
#### Two builds → regression narrative ![](../images/readme/h4.svg)

1. Open baseline and candidate as tabs; match cursor scope if needed.
2. **Trace Compare** template, or `compare_performance` then `regression_explain`.
3. Act only on High/Medium confidence deltas that Statistics on both tabs reproduce.
4. Optional: `optimize_experiment` on the candidate’s hottest task to sketch mitigations (still heuristic).

<a id="example-explain-region" name="example-explain-region">&#x200B;</a>
#### Cursor window → Explain region ![](../images/readme/h4.svg)

1. Place **C1** / **C2** on the phase of interest (e.g. 1.060 s … 1.120 s); enable **Limit to C1–Cn**; re-open Analysis.
2. Right-click the timeline → **Explain this region with AI** (or AI panel → **Explain region**).
3. Confirm the user turn lists `Cursor region window: jump:lo … jump:hi`. Reject any `jump:TIME` outside that window.
4. Follow up with `correlate_events` / `query_raw_metric` on tasks named in-window; bookmark evidence times.

<a id="example-verify-pi" name="example-verify-pi">&#x200B;</a>
#### Priority inversion finding → Verify ![](../images/readme/h4.svg)

1. Open Analysis Findings; select a Priority Inheritance / inversion row.
2. **Verify with AI…** (or **Auto investigate…** for a longer chain).
3. Expect `detect_priority_inversion` / `query_raw_metric` (priority_inheritance) / `find_critical_path`; read the Evidence score and investigation tree.
4. Click in-scope `jump:TIME` links; confirm L/M/H on the timeline and in Priority Inheritance statistics.

<a id="simulator-limits" name="simulator-limits">&#x200B;</a>
### Simulator limits ![](../images/readme/h3.svg)

| Does | Does not |
|------|----------|
| Replay measured slices / migrations / blocking gaps for the Statistics scope | Run FreeRTOS scheduling, ISRs, or cache models |
| Score pin / priority / contention / migration experiments | Guarantee WCET or deadline after a firmware change |
| Label every result as estimate / not measured | Replace timeline verification or a new capture |

Phrase changes as **pin / affinity / priority / mutex / migration** so the simulator engages; vague text falls back to a qualitative estimate (`simulator: none`).

---

<a id="endpoints-and-models" name="endpoints-and-models">&#x200B;</a>
## Endpoints and models ![](../images/readme/h2.svg)

Any OpenAI-compatible endpoint works, including Ollama (`http://localhost:11434/v1`). Chat requests time out after 120s (**Stop** still cancels sooner). Give the endpoint at least an **8k** context window so a full Findings card plus a tool round still fits.

**Local models:** the shipped Ollama default is `phi4-mini:3.8b` (light triage). For reliable native function calling prefer `qwen2.5:7b` / `qwen2.5:14b` or `llama3.1:8b` (or larger). 3B-class models often skip tools and emit ` ```btftool ` fences instead.

**Import presets:** [`examples/ai`](examples/ai/README.md) ships [`ollama.json`](examples/ai/ollama.json), [`gemini.json`](examples/ai/gemini.json), [`openai.json`](examples/ai/openai.json), [`deepseek.json`](examples/ai/deepseek.json), [`grok.json`](examples/ai/grok.json), and [`presets.json`](examples/ai/presets.json). Imported values fill **Settings → AI**; review and confirm to save. Each preset keeps its own base URL, model, key, auth mode, and TLS flag.

Keys may also come from the environment as `OPENAI_API_KEY`, `GEMINI_API_KEY`, or `OLLAMA_API_KEY` (`VITE_*` prefixed on the web). A local Ollama endpoint needs no key.

<a id="capability-matrix" name="capability-matrix">&#x200B;</a>
### AI capability / model matrix ![](../images/readme/h3.svg)

| Capability | Local 3B | Local 7B+ | Cloud |
|---|:--:|:--:|:--:|
| Basic Q&A | ✓ | ✓ | ✓ |
| Tool calling | △ | ✓ | ✓ |
| Investigation (`investigate` / root-cause chain / hypotheses) | △ | ✓ | ✓ |
| Complex reasoning (multi-step correlation, alternatives) | △ | ✓ | ✓ |
| Large traces (big Findings card / long chat history) | △ | △ | ✓ |
| What-if / optimize (`what_if`, `optimize_experiment`) | ✓ | ✓ | ✓ |

✓ reliable · △ inconsistent — works sometimes but often skips native tool calls, hallucinates numbers, or truncates on long context; always verify against the timeline before trusting a result.

**Which model should I use?**

| If you… | Use |
|---|---|
| Want quick triage / a sanity check | Local 3B (shipped `phi4-mini:3.8b`) — fast, no key, but confirm every claim on the timeline |
| Need reliable tool calling (Investigate, Root cause, Verify, Explain region, Auto investigate, Ask AI about this event, What-if, Optimize) | Local 7B+ (`qwen2.5:7b`, `qwen2.5:14b`, `llama3.1:8b`, or larger) |
| Have a large scope (many findings, long chat) or want the strongest reasoning | Cloud (`gpt-4o`, Gemini, DeepSeek, Grok) — mind the [privacy](#what-leaves-the-machine) trade-off |
| Handle confidential traces | Local Ollama regardless of size — nothing leaves the machine |

3B-class local models often skip native tool calls and emit a fenced ` ```btftool ` block instead — the viewer renders the same GUI cards either way (see [GUI tools](#gui-tools)) — but investigation-heavy templates (Investigate / Root cause / Verify / Explain region / Auto investigate / Ask AI about this event / What-if / Optimize) need a tool-capable model to reliably chain multiple calls.

### Credential storage

| | Desktop | Web |
|--|---------|-----|
| Where keys live | `[ai] *_api_key` in `btf_viewer.rc` next to the viewer | Browser `localStorage` (`btf-viewer-settings-v1`) |
| At rest | Encrypted as `enc1:…` (machine-bound; not portable to another host) | **Plaintext** in localStorage — treat as convenience only |
| Sent to the model | Never as a chat field; only as the HTTP `Authorization` / API header to the configured endpoint | Same |
| Clear | Settings → AI → clear key, or delete `btf_viewer.rc` AI keys | Settings → Reset / clear site data |

### What leaves the machine

```text
What AI receives
✓ Analysis Findings (titles, severities, task names, heuristic text)
✓ Selected metrics / tool results the model requests
✓ Scoped timeline search hits and correlate windows
✓ Trace Compare CSV when that template runs
✓ User question + short chat history

What AI does NOT receive
✗ Raw .btf / .btf.gz file bytes
✗ The full unrequested event stream
✗ API keys inside the prompt body
```

| | Local Ollama | Cloud endpoint |
|--|--------------|----------------|
| Trace file stays local | ✓ | ✓ |
| Findings / metrics leave the machine | No (loopback) | Yes — to that vendor |
| Raw BTF uploaded | No | No |
| API key required | Usually no | Usually yes |

Prefer local Ollama for confidential traces. Redact sensitive task names in annotations before using a cloud preset.

---

<a id="gui-tools" name="gui-tools">&#x200B;</a>
## GUI tools ![](../images/readme/h2.svg)

The model may call several tools in one turn; they apply as a single batch. With **Auto-apply GUI actions** off (default in **Settings → AI**), each mutating batch shows **Apply** / **Skip** and **Undo**, plus **Apply GUI actions** under the log. Read-only `query_raw_metric` / `search_timeline` / `trigger_compare` / `investigate` / `detect_anomalies` / `correlate_events` / `find_critical_path` / `compare_performance` / `generate_report` / `check_budget` / `optimize` / `regression_explain` / `investigation_replay` / `what_if` / `optimize_experiment` / `analyze_traces` / `baseline_score` / `recommend_experiments` / `detect_priority_inversion` / `find_related_findings` / `compare_tasks` / `explain_finding` / `interpret_query` / `validate_experiment` / `manage_hypotheses` batches run immediately (no Apply card).

| Tool | Parameters / targets | Effect |
|------|----------------------|--------|
| `set_cursors` | `timestamps` (1–8 trace times) | Place cursors (enables **Limit to C1–Cn** when two or more) |
| `zoom_to_range` | `start_time`, `end_time` | Focus the timeline between two times |
| `highlight_task` | `task_name_or_id` (display name, numeric id, or merge key) | Lock-highlight a task row. Unknown names are ignored so the timeline is not dimmed. Empty string clears. |
| `set_view_mode` | `mode` (`task` / `core`); optional `orientation` | Switch Task or Core view; horizontal or vertical |
| `open_corridor_inspector` | optional `core_from` / `core_to` (`Core_0`, `0`, `c0`, `Core 0`) | Open Migration Inspector; aliases resolve the same way |
| `add_annotation` | `time`, `note` (≤240 chars) | Pin an orange timeline note at a timestamp (stays on the current right-panel tab) |
| `query_raw_metric` | `task`, `metric` (`priority_inheritance`, `execution`, `migrations`, `blocking`, `sync`, `findings`) | Read-only: return the per-task series for the current Statistics scope (up to 40 rows) |
| `export_report` | optional `format` (`html` / `csv` / `json`) | Download HTML/CSV/JSON bundling Analysis Findings, mermaid diagrams from the chat, annotations, and GUI state (cursors / highlight / view); `json` saves a full investigation package (see `export_investigation`). |
| `clear_marks` | optional `what` (`annotations` / `cursors` / `bookmarks` / `all` / `everything`) | Clear AI clutter. `all` (default) drops annotations + cursors; `everything` also clears bookmarks |
| `reset_view` | (none) | Fit the timeline to the full span and clear the task highlight (marks stay) |
| `search_timeline` | `query`; optional `mode` (`contains` / `exact` / `regex` / `sti` / `tags` / `intervals` / `lifecycle` / `pointers` / `migrations`) | Find-panel search; returns matching timestamps (up to 40) |
| `trigger_compare` | optional `tab_a` / `tab_b` (0-based tab index or filename) | Read-only Trace Compare CSV + open the compare dialog (needs two loaded tabs) |
| `investigate` | optional `finding_id`, `depth` (1–5) | Read-only: investigation graph with root-cause chain, hypotheses, ranked anomalies, suggested tools |
| `detect_anomalies` | optional `limit` (1–40) | Read-only: rank Analysis Findings as Critical / Warning / Info |
| `correlate_events` | `task`; optional `around_time`, `window` | Read-only: merge blocking / execution / migration / sync / priority / Find hits into one timeline |
| `find_critical_path` | `task`; optional `timestamp`, `window` (default 2000) | Read-only: preempt/block/mutex critical path around a timestamp; also returns a `mermaid` graph (`graph LR`), `graph_nodes` (id/label/kind/time), and split `blocking_steps` / `preemption_steps` arrays |
| `compare_performance` | optional `tab_a` / `tab_b` | Read-only: structured A vs B metric deltas + confidence (two tabs); `data.regression_type` classifies the primary delta as `execution` / `scheduling` / `synchronization` / `migration` / `load_balance` / `unknown` (legacy `classification` values like `thrashing` / `load_imbalance` / `tick_health` are preserved alongside it) |
| `generate_report` | optional `report_type`, `finding_id` | Read-only: typed engineering markdown (`executive` / `performance` / `root_cause` / `regression` / `optimization` / `bug` / `ci`); call `export_report` to save |
| `check_budget` | optional `budgets`, `tasks` | Read-only: compare per-task WCET/response/deadline metrics against budgets (host builds rows from findings when `tasks` omitted) |
| `optimize` | optional `limit` (default 5) | Read-only: evidence-backed mitigation ideas (estimate disclaimer) |
| `regression_explain` | optional `tab_a` / `tab_b` | Read-only: compare two tabs then narrate the primary regression; includes the same `regression_type` classification |
| `bookmark_finding` | `time`, `kind` (`root_cause` / `evidence` / `correlated` / `reference`); optional `note` | GUI: pin a semantic investigation annotation (Apply required) |
| `investigation_replay` | optional `finding_id`, `conclusion`, `tools_run`, `evidence_times` | Read-only: structured investigation replay card |
| `what_if` | `change`; optional `task` | Read-only: heuristic slice-replay what-if (migrations / blocking / load balance; not FreeRTOS kernel) |
| `optimize_experiment` | optional `task`, `limit` (1–12, default 5) | Read-only: run ranked automatic pin/priority/contention/migration experiments |
| `analyze_traces` | (none) | Read-only: rank all loaded tabs by scheduling behavior |
| `baseline_score` | optional `task`, `baseline`, `snapshot` | Read-only: score current per-task metrics (WCET/blocking/migrations/response) against the stored historical baseline; flags `\|z\|>2` |
| `recommend_experiments` | optional `finding_id`, `task`, `limit` (1–20, default 5) | Read-only: suggest simulation / firmware / measurement validation experiments from findings heuristics |
| `export_investigation` | optional `finding_id`, `conclusion`, `tools_run`, `evidence_times` | Download the completed investigation (finding, tools run, queries, evidence, conclusion, confidence, alternatives) as a JSON package |
| `detect_priority_inversion` | optional `task`, `window` | Read-only: scan priority-inheritance boost episodes for L/M/H inversion suspects (high/medium/low task, mutex, time, duration) |
| `find_related_findings` | optional `finding_id`, `task`, `metric`, `window`, `limit` (1–40, default 10) | Read-only: relate Analysis Findings by shared task, metric keyword, evidence-time proximity, or severity adjacency |
| `compare_tasks` | `task_a`, `task_b`; optional `metrics` | Read-only: side-by-side execution/blocking/migrations/priority-inheritance delta table between two tasks |
| `explain_finding` | optional `finding_id`, `level` (`quick` / `technical` / `deep`) | Read-only: explain one Analysis Finding at the chosen depth (host-side; uses finding text plus hypotheses) |
| `interpret_query` | `question` | Read-only: turn a free-form question into an explicit investigation mode/scope before other tools run |
| `validate_experiment` | optional `expected`, `actual` (metric → signed percent) | Read-only: compare expected experiment deltas with actual A vs B / what-if results (`VALIDATED` / `PARTIALLY VALIDATED` / `DISPROVED`) |
| `manage_hypotheses` | `hypothesis_id`, `status` (`supported` / `possible` / `rejected` / `need_evidence`); optional `reason`, `finding_id` | Read-only: mark one investigation hypothesis status |

Models without native tool calling can emit a fenced ` ```btftool ` JSON block (same cards). Prefer a tool-capable model (see [Endpoints and models](#endpoints-and-models), or `gpt-4o` / Gemini) if native calls stay silent.

After **Apply**, **Undo last actions** restores zoom / view / highlight / inspector / marks; **Ctrl/Cmd+Z** also reverts cursors and marks.

---

<a id="diagrams" name="diagrams">&#x200B;</a>
## Diagrams ![](../images/readme/h2.svg)

Replies may include ` ```mermaid ` **sequence** diagrams (mutex take/give, block/resume, priority boost / L/M/H) and `graph LR` / **flowchart** core-migration graphs (counts on edges). Pipe **Markdown tables** (and a sanitized HTML `<table>` copied from Findings) render as HTML tables in the reply pane. The Evidence panel adds its own auto-generated `graph TD` **Investigation tree** (root-cause chain steps as boxes, alternative hypotheses as rounded nodes branching off the finding) whenever `investigate` returns a chain — same renderer, same click/zoom rules below.

- Click a **task** node to lock-highlight that timeline row (`Low[266] (Core 0)` resolves to `Low[266]`).
- Click a **core** node (`Core_0`, `C0`, `C1`) to switch to Core View and scroll to that core.
- Mutex hex and other unresolved labels do nothing (the timeline stays undimmed).
- Click empty figure area to open a larger zoom window (scroll to zoom 0.5–6×; **Esc** or **Close**). Trackpad pinch is treated as scroll.
- The link row under the figure has the same targets.
- **Save As…** HTML keeps inline SVG with clickable nodes (chat zoom wrappers are omitted).

---

<a id="desktop-vs-web" name="desktop-vs-web">&#x200B;</a>
## Desktop vs web ![](../images/readme/h2.svg)

| Area | Desktop | Web |
|------|---------|-----|
| Native tools + ` ```btftool ` | Same schema and cards | Same |
| `add_annotation` / `query_raw_metric` / `export_report` | Marks + scoped series + save dialog | Same (browser download) |
| `clear_marks` / `reset_view` / `search_timeline` / `trigger_compare` / `investigate` / `detect_anomalies` / `correlate_events` / `find_critical_path` / `compare_performance` / `generate_report` / `check_budget` / `optimize` / `regression_explain` / `investigation_replay` / `what_if` / `optimize_experiment` / `analyze_traces` / `baseline_score` / `recommend_experiments` / `export_investigation` / `bookmark_finding` / `detect_priority_inversion` / `find_related_findings` / `compare_tasks` / `explain_finding` / `interpret_query` / `validate_experiment` / `manage_hypotheses` | Same | Same (compare overlay; search uses Find; investigation tools are read-only except `bookmark_finding`) |
| `highlight_task` / corridor cores | Same resolve rules | Same |
| In-chat mermaid figure | Data-URI image + node hit-test | Inline SVG node clicks |
| In-chat Markdown / HTML tables | Same rendered table | Same |
| Zoom window + link row | Scroll to zoom + link row | Same |
| Ask AI about this event (segment context menu) | Same composed prompt, `panel.ask_event(...)` | Same, `askTemplate('ask_event', prompt)` |
| Explain this region with AI (≥2 cursors) | Same `explain_region` + injected `jump:lo…hi` window | Same |
| Investigation tree (Evidence panel) | Same `graph TD` generator, rendered inline | Same |
| Evidence Quality + validator | Heuristic band, coverage, falsify checks, claim guard | Same |
| Authentication | Settings → AI → None / API key / Sign in; panel chip + 401 CTAs until a successful turn | Same (`VITE_*` env keys) |
| Self-signed TLS | **Allow self-signed TLS** per preset skips HTTPS certificate checks | Persist the same flag + tip; browsers still verify — trust the cert, use `http://`, or use Desktop |
| Model picker | Editable combo; refresh fills and opens the dropdown | Same |
| Fonts | **pt** | **px** |
| Endpoint from `file://` | N/A | CORS — prefer Vite proxy, or [Opening the web app from `file://`](#opening-the-web-app-from-file) |

---

<a id="troubleshooting" name="troubleshooting">&#x200B;</a>
## Troubleshooting ![](../images/readme/h2.svg)

| Symptom | Cause | Try |
|---------|-------|-----|
| Web: Failed to fetch / CORS | Browser blocked a cross-origin call (`file://` sends `Origin: null`) | Prefer `npm run dev` / `make preview` (both proxy Ollama), or see [Opening the web app from `file://`](#opening-the-web-app-from-file) |
| 401 / 403 | Missing or rejected key / origin | Settings → AI → Sign in or API key (`OPENAI_API_KEY` / `GEMINI_API_KEY` / `OLLAMA_API_KEY`; local Ollama needs none) |
| `CERTIFICATE_VERIFY_FAILED` / self-signed TLS | Private CA or self-signed HTTPS gateway | Desktop: Settings → AI → **Allow self-signed TLS**. Web: trust the cert in the OS/browser, use `http://` on a private LAN, or use the Desktop app |
| Chat probe timed out / `The read operation timed out` | `GET /models` lists ids only; inference is slow or hung | **Test connection** POSTs `/chat/completions` (non-streaming, 120s). Warm the model (`ollama run MODEL`) and retry. Debug with the curl probe below; if curl hangs too, the gateway's chat upstream is stuck. Try `"stream": true` if non-stream never returns. Lower context length on a VRAM-tight local host. |
| Model not found | Typed id is not served | Refresh the Model list (or Test connection) and pick a served id from the dropdown, or `ollama pull` it |
| Gemini HTTP 400 `thought_signature` | Gemini 3 requires a thought blob on tool follow-ups | Retry the question — the viewer echoes Gemini thought signatures |
| Raw ` ```btftool ` JSON instead of native tool calls | Model lacks (or skips) function calling | Same cards either way (one object, JSON array, or several objects per fence) — **Apply** or enable **Auto-apply GUI actions**. Switch to `qwen2.5:7b` / `llama3.1:8b` / `gpt-4o` / Gemini for native calls |
| Ask times out (over 120s) or stays on Waiting… | Cold start, CPU offload, or VRAM spill | **Stop**, warm with `ollama run MODEL`, retry. Use **Clear** between long threads. Smaller model or shorter Statistics scope if the Findings card is huge |
| Later turns ignore earlier facts | Chat history exceeded the context window | **Clear** on the AI bar, or **Analysis → Query with AI…** for a fresh scoped prompt |
| Need raw AI request/response dumps (Desktop) | Debugging tool rounds / provider quirks | Settings → AI → **Log MCP messages to file** (off by default). Appends to `./ai_mcp_messages.log`; delete when finished |

<a id="test-connection-curl" name="test-connection-curl">&#x200B;</a>
### Test connection curl ![](../images/readme/h3.svg)

Same body the viewer sends for **Test connection** (replace `BASE`, `MODEL`, and `KEY`):

```bash
curl -vk --max-time 180 \
  -H "Authorization: Bearer KEY" \
  -H "Content-Type: application/json" \
  -d '{"model":"MODEL","stream":false,"messages":[{"role":"user","content":"Reply with exactly: OK"}],"max_tokens":8}' \
  BASE/chat/completions
```

---

<a id="opening-the-web-app-from-file" name="opening-the-web-app-from-file">&#x200B;</a>
## Opening the web app from `file://` ![](../images/readme/h2.svg)

A page opened straight from disk sends `Origin: null`, which Ollama rejects with
`403` — the browser then reports only `Failed to fetch`. Serving the app over
http avoids this entirely (`npm run dev` / `make preview` proxy Ollama for you),
and the Desktop app is not affected at all.

To keep using `file://`, allow every origin on the Ollama side:

```bash
# Server started from a terminal
OLLAMA_ORIGINS="*" ollama serve

# macOS menu-bar app (Ollama.app) — a shell variable does not reach it
launchctl setenv OLLAMA_ORIGINS "*"   # then quit Ollama and reopen it
```

Verify the change took effect; expect `200` and an `Access-Control-Allow-Origin`
header:

```bash
curl -s -D - -o /dev/null -H "Origin: null" http://localhost:11434/v1/models \
  | grep -iE "^HTTP|access-control-allow-origin"
```

If a `file://` page is still refused, list the null origin explicitly with
`OLLAMA_ORIGINS="*,null"`. Note that `*` lets **any** page you visit reach your
local models; undo it with `launchctl unsetenv OLLAMA_ORIGINS` when done.

---

<a id="cli-regression-gate" name="cli-regression-gate">&#x200B;</a>
## CLI regression gate ![](../images/readme/h2.svg)

Desktop headless CI can compare a candidate trace to a baseline and optionally ask the configured AI for a short narrative:

```bash
python builds/btf_viewer.py analyze candidate.btf --baseline baseline.btf --fail-on-regression
python builds/btf_viewer.py analyze candidate.btf --save-baseline /tmp/base.json
python builds/btf_viewer.py analyze candidate.btf --baseline /tmp/base.json --fail-on-regression --ai
python builds/btf_viewer.py ai-test --dataset tests/ai --fail-under 70
```

Or `make -C BTFViewer ai-test` (`AI_DATASET`, `AI_FAIL_UNDER`).

See also [Export → Headless CLI](README.md#headless-cli-desktop-only) in the user guide.
