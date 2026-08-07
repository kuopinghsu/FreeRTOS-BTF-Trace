# BTF Viewer — Application Notes

Top-down workflows for analysing RTOS scheduler behaviour with BTFViewer. Start at the system level, follow Analysis findings, then open the Statistics sections they name.

---

## Table of Contents

| Section | Purpose |
|---------|---------|
| [1. Load a trace](#1-load-a-trace) | Open a file and orient |
| [2. Top-down analysis ladder](#2-top-down-analysis-ladder) | Inspection order for any new trace |
| [3. Worked example — `example-8cores`](#3-worked-example--example-8cores) | Walkthrough with measured stats |
| [4. Deep-dive playbooks](#4-deep-dive-playbooks) | Short procedures per metric |
| [5. Scope, compare, and custom signals](#5-scope-compare-and-custom-signals) | Cursors, Trace Compare, tags |
| [6. Export results](#6-export-results) | Findings, CSV/HTML, Perfetto, CLI |
| [7. AI Assistant flow](#7-ai-assistant-flow) | Ollama chat over Analysis Findings |
| [Quick-reference](#quick-reference-metric-to-root-cause) | Symptom → metric map |

---

## 1. Load a Trace

```bash
python btf_viewer.py {tracefile}
```

**File → Open** (`Ctrl+O`) or drag-and-drop. Supported: `.btf`, `.btf.gz`, `.bz2`, `.zip`. On the web viewer, open `btf_viewer.html`.

![BTF Viewer — timeline with CPU Load graph and Statistics](../images/btfviewer.png)

*Timeline, CPU Load, and Statistics on first open.*

| Step | Action |
|------|--------|
| 1 | Status bar + `Ctrl+0` — confirm span; Fit to Window |
| 2 | Toolbar **Core** or **Task** + **Load** — orient on cores or tasks |
| 3 | **Statistics** + **Analysis** — summary metrics and heuristic triage |
| 4 | **Trace Health (TICK)** — confirm timer health before trusting derived timing |

For migration analysis, see [§3.5](#35-concurrency--migrations-locks-priority-inheritance) and [§4.5](#45-core-migrations).

---

## 2. Top-Down Analysis Ladder

Work down this hierarchy. Stop when the evidence explains the symptom.

```text
① System health     Trace Health (TICK), span, instrumentation flags
② Core balance      Core Utilisation + Load Balance Score
                    → Core Time Breakdown / Concurrent Core Active / Switch Overhead
③ Task CPU / WCET   Top Tasks → Execution Time Per Slice (Max)
④ Latency           Blocking Time → Dispatch Latency → Preemption Chain
⑤ Concurrency       Core Migrations → Mutex/Semaphore → Priority Inheritance
⑥ Compliance        Deadlines / Affinity / Task Lifecycle / Tags / Intervals
```

Default Statistics order matches this ladder (after Summary): utilisation → health → breakdown → concurrency → switch overhead → top tasks → migrations → … → tags. CSV/HTML export uses the same order.

**In the UI**

1. Open toolbar **Analysis** and read each finding.
2. Open the Statistics section named by the finding.
3. Click **Max**, scatter points, or heatmap cells to jump the timeline.
4. Place cursors (`C`) around the phase of interest and enable **Limit to cursor range**.
5. Optionally open the **AI** tab and ask Ollama to triage the same findings ([§7](#7-ai-assistant-flow)).

**Demo traces:** `example-8cores.btf.gz` concatenates intentional stress tests. Scope to a phase before treating a warning as a product defect.

---

## 3. Worked Example — `example-8cores`

### 3.0 Trace snapshot

| Field | Value |
|-------|-------|
| File | `tracedata/example-8cores.btf.gz` |
| Span | **2.358 s** (`#timeScale us`) |
| Cores / tasks / segments / STI | **8** / **154** / **31 141** / **33 495** |
| Context switches / migrations | **31 133** / **18 992** |
| Instrumentation | priority + sync + intervals |
| TICK | **WARNING / TICKLESS** — CV **35.9 %**, missed ≈ **8** |

Open **Statistics**, then **Analysis**.

---

### 3.1 System health (TICK)

**Statistics → Trace Health (TICK)**

| Metric | Measured |
|--------|----------|
| Mode | **TICKLESS** (CV 35.9 % ≫ 5 % threshold) |
| Avg period / max gap | 944 µs / 2.481 ms |
| Missed ticks (est.) | 8 |

![Tick interval distribution — example-8cores](../images/stats/stats-tick.svg)

*2496 TICK events; multi-tick gaps often fall in idle stretches between suite phases.*

Tickless idle is active. Large gaps between ticks are not, by themselves, proof of a lost interrupt during busy work. Scope to a busy phase before chasing missed ticks. For tickless vs tickful trade-offs, see [§5.2](#52-compare-two-builds).

---

### 3.2 Core balance

**Statistics → Core Utilisation**

| Metric | Measured |
|--------|----------|
| Core_0 … Core_7 (excl. IDLE/TICK) | 68.7 … **77.3 %** |
| Load Balance Score | **95 %** (G = 0.049, σ = 6.0 %) |

Score ≥ 85 % and σ ≤ 30 % → reasonably balanced. Imbalance is not the primary issue on this sample; still check migrations—good balance can coexist with expensive bouncing.

| Next section | What to look for |
|--------------|------------------|
| **Core Time Breakdown** | Elevated **Gap %** often tracks switch overhead |
| **Concurrent Core Active** | Time with *N* cores busy; click a row for the duration chart |
| **Kernel Switch Overhead** | Per-core switch gaps; click a row for the distribution |

![Concurrent core active (N=4) — example-8cores](../images/stats/stats-concurrency-4.svg)

*Interval dwell while exactly 4 cores run non-IDLE/non-TICK work.*

![Kernel switch overhead on Core_0 — example-8cores](../images/stats/stats-switch-core0.svg)

*Context-switch gaps on Core_0 (`t_resume,B − t_preempt,A`).*

---

### 3.3 Task CPU and WCET

Top Tasks (excl. IDLE/TICK) are dominated by equal-priority CS workers:

| Task | CPU % | Max slice | p95 |
|------|-------|-----------|-----|
| CS[28] | 15.9 % | **3.623 ms** | 1.631 ms |
| CS[11] / CS[24] | ~15 % | ~2.5–3.3 ms | ~1.6 ms |

Also notable: `Med[267]` (~6 %), mutex/semaphore workers (~5–6 %).

**Procedure:** **Execution Time Per Slice** → sort by **Max** → click **Max** to zoom the WCET slice. Worst slices (~3–4 ms) are long relative to a 1 ms tick.

- Cap concurrency of equal-priority workers, or pin with `vTaskCoreAffinitySet`.
- Set deadlines under **Settings → Display → Analysis thresholds** (values in **ns**; e.g. `CS[28]=2000000` = 2 ms) and review **Deadlines / CPU budget**.
- On a long Max slice, check Preemption Chain and Mutex.

---

### 3.4 Latency

**Statistics → Blocking Time** (off-CPU gap until next resume)

| Task | Max block | Notes |
|------|-----------|-------|
| High[268] | **52.865 ms** | High waiter during inversion demo |
| Low[266] / Med[267] | ~35–40 ms | Expected around test 8 |
| CS[*] | ~5–6 ms | Peer contention + migration |
| Runner[1] | 737 ms | Orchestrator sleep — ignore |

Scope cursors to the inversion window (`Low`/`Med`/`High` ≈ 3.085–3.310 s). Cross-check **Preemption Chain** (e.g. `CS[25]←CS[19]`). For ready→run delay (create / `vTaskResume` → first switch-in), open **Dispatch / Scheduling Latency** — sync wakes are not attributed yet. Click a row for the distribution; **Min** / **Max** jump to extremes.

![Dispatch latency for SR0[271] — example-8cores](../images/stats/stats-dispatch-sr0.svg)

*Lifecycle test task SR0: create/resume → next switch-in samples.*

---

### 3.5 Concurrency — migrations, locks, priority inheritance

#### Core migrations

| Task | Migrations | Rate | Avg dwell | Ping |
|------|------------|------|-----------|------|
| CS[18] | 586 | **1692 /s** | 476 µs | 24 |
| CS[21] / CS[12] | ~580 | ~1.6k/s | ~0.5 ms | ~20 |

Trace-wide: **18 992** migrations. Hottest pairs (`Core_5→Core_7`, …) are mostly **0 % lock-bounce** — scheduling thrash from test 1, not lock contention.

| Signal | Meaning |
|--------|---------|
| High **Ping** + high **Rate** / short **Dwell** | Rapid A↔B thrashing (Ping = A→B→A within 1 µs) |
| High **Migr**, low **Ping** | Spreads across cores without oscillation |
| Elevated **Bounce %** on a busy pair | Migration while a mutex/queue hold is active |

**Procedure:** sort Migrations by **Ping** or Rate → click for Rate/Dwell charts → lock-highlight the task in **Task** view + **Load**. For lock-bounce: **Core-Pair Migration Summary** → sort by Bounce % → Gap chart (orange = bounce) → confirm in **Mutex / Semaphore → Bounces**. Details: [§4.5](#45-core-migrations).

![CS[22] highlighted in Task View with per-core CPU Load](../images/stats/tasks-cpu-load-cs22.svg)

*`CS[22]` locked in Task View; CPU Load shows that task’s share per core.*

#### Mutex / semaphore / queue

| Object | Holds | Bounces | Status |
|--------|-------|---------|--------|
| mutex `0x80021920` | 864 | 6 | Warning |
| queue `0x80021990` | 864 | **858** | OK status, extreme bounce |

Co-locate tasks that share a hot mutex/queue. Investigate Warning rows on the timeline (demo teardown can leave unpaired STI).

#### Priority inheritance

| Task | Base→Peak | Boosted time | Pattern |
|------|-----------|--------------|---------|
| Low[266] | 2→4 | **103.318 ms** | **Mutex inherit** |
| PS[228] | 2→4 | 119 µs | **L/M/H pattern** |

![Priority inversion — red inherit stripes on Low](../images/stats/tasks-priority-low.svg)

*Red bottom stripes on `Low[266]` during test 8 (`priority_inherit` → `priority_disinherit`).*

Kernel inheritance on `Low[266]` is working. Treat any **L/M/H** row as a design review. Doc snapshot window: `--lo 3042000 --hi 3359000` (µs).

---

### 3.6 Compliance — affinity, suspend/resume, tags

- **Core Affinity** — `Aff[*]` masks match observed cores; `AffM[299]` remask OK. **No violations.**
- **Task Lifecycle** — `SR0`…`SR3` Susp/Res **4/4**; no run between `suspend` and `resume`.
- **Tag Analysis → `tag0_event`:** 2357 samples (avg ≈ 34 631, p95 41 936). Bind channels to real budgets; compare builds with Trace Compare.

![tag0_event distribution](../images/stats/stats-tag0.svg)

---

### 3.7 Performance verdict

| Priority | Finding | Product action |
|----------|---------|----------------|
| P0 | CS migration thrash (~1.6k/s, dwell ~0.5 ms) | Affinity-pin hot tasks; reduce equal-priority fan-out |
| P0 | Queue core bounces (**858**) | Co-locate producers/consumers; shorten holds |
| P1 | L/M/H on `PS[228]`; High Max block ~53 ms | Keep inheritance; audit critical sections; set deadlines |
| P1 | WCET CS Max ~3.6 ms vs 1 ms tick | Budget slices; verify under tickful config |
| P2 | TICKLESS CV 35.9 % | Scope busy windows before chasing missed ticks |
| OK | Load Balance 95 %; Affinity + SR 4/4 | Keep as CI checks (`report` HTML) |

Success criteria after a fix (Trace Compare Δ): lower CS Migr rate / Ping, lower queue Bounces, stable or improved High Max block, Load Balance Score ≥ 85 % with σ ≤ 30 %. See [§5.2](#52-compare-two-builds).

---

## 4. Deep-Dive Playbooks

Short procedures when Analysis or the ladder points at a metric. Examples assume `example-8cores` unless noted.

### 4.1 Core utilisation and load balance

1. **Core Utilisation** — active (non-IDLE, non-TICK) CPU%; badge amber when σ > 30 %.
2. **Analysis** warns when Score < 70 % or σ > 30 %; “reasonably balanced” when Score ≥ 85 % and σ ≤ 30 %.
3. **Core Time Breakdown** — high Gap % → **Kernel Switch Overhead**.
4. **Concurrent Core Active** — click level *N* for dwell distribution (`snapshot … --metric concurrency --active-cores N`).
5. **Kernel Switch Overhead** — click a core for switch-gap distribution (`… --metric switch_overhead --core Core_N`).
6. **Top Tasks by CPU** — who consumes the budget.

| Symptom | Next |
|---------|------|
| One core > 90 %, others idle | **Core Affinity** |
| All high, one low | **Mutex/Semaphore**, **Preemption Chain** |
| Rarely *N* cores busy together | **Concurrent Core Active**; affinity / worker count |
| High Gap % or switch Max | **Kernel Switch Overhead**; ISR / critical sections |

### 4.2 WCET (execution time per slice)

1. **Execution Time Per Slice** → sort **Max** → click **Max**.
2. Check neighbours on the core and **Preemption Chain** for that victim.

### 4.3 Blocking / scheduling delay

1. **Blocking Time** → sort **Max** / **p95**.
2. Long gap → **Preemption Chain** and **Mutex/Semaphore**.
3. Scope away from orchestrator sleeps (`Runner`).
4. **Dispatch / Scheduling Latency** — ready→run from STI `resume Name[id]` / create → next switch-in (`… --metric dispatch --task …`). Sync-object wakes are not attributed yet.

Blocking is the off-CPU gap until the next resume, not release-to-completion response time. Dispatch answers a different question: how long from *known ready* until the task runs.

### 4.4 Priority inversion

1. **Priority Inheritance** (needs `priority_inherit` / `priority_disinherit` STI).
2. Patterns: **Mutex inherit**, **L/M/H**, **Boost only**.
3. Timeline: red bottom stripe on the holder; distribution chart → click a point to jump.

### 4.5 Core migrations

1. **Core Migrations** — sort by **Rate**, **Dwell**, **Ping**. High Rate + short Dwell + high Ping → thrashing.
2. **Core-Pair Migration Summary** — **Bounces** / **Bounce %** = lock held across the hop.
3. **Task** view + lock-highlight + **Load** for per-core CPU Load (`snapshot … --view-mode task --task … --cpu-load`).
4. Toolbar **Heatmap** / **Chord** — **Bounce Only** for lock-bounce.
5. **Mutex / Semaphore → Bounces** — object-level confirmation.

### 4.6 Tick health

1. **Trace Health (TICK)** — mode, CV, large gaps, missed estimate.
2. **Tick Distribution…** for scatter/histogram.
3. On tickless systems, re-evaluate inside a cursor-scoped busy window.

### 4.7 Mutex / semaphore correctness

1. **Mutex / Semaphore** — Issues, Bounces, Status.
2. Warning rows → timeline STI `take`/`give`; check delete-while-held.
3. High Core bounce → pin sharers or redesign ownership.

### 4.8 Task suspend / resume

1. **Task Lifecycle** — Susp/Res must match (`SR*` → 4/4 on this sample).
2. Timeline: no run between `suspend` and `resume`.

### 4.9 Deadlines and CPU budgets

**Settings** (`Ctrl+,`) → **Display → Analysis thresholds** (or the link inside **Deadlines / CPU budget**):

| Threshold | Example |
|-----------|---------|
| CPU budget % | `25` |
| Task deadlines | `CS[28]=2000000` (**ns**) → 2 ms in this trace’s time unit |

Then expand **Deadlines / CPU budget**: click a violating slice to jump and annotate; scope with cursors + **Limit to cursor range**. Exports include both violation tables when thresholds are set.

---

## 5. Scope, Compare, and Custom Signals

### 5.1 Cursor-scoped analysis

| Action | Effect |
|--------|--------|
| Left-click | Place / remove cursor |
| `Shift`+click | Snap to segment edge |
| `C` | Cursor at viewport centre |
| `Ctrl+R` | Zoom to C1…Cn |
| **Limit to cursor range** | Statistics + Analysis recompute for C1–Cn |

![Cursors C1–C3 with Δ badges](../images/example.png)

| Metric | Cursor rule |
|--------|-------------|
| CPU % | Overlap ÷ range width |
| Execution slices | Fully inside range |
| Blocking | Both slices inside |
| Migrations | Overlapping events |

### 5.2 Compare two builds

1. Open two tabs → Statistics footer **Trace Compare…**.
2. Review Summary (load balance + tick), Top Tasks, Core Util, Migrations, Execution, Blocking, Preemption, Sync.
3. **Δ** = A − B. Export CSV/HTML from the dialog.

```bash
python builds/btf_viewer.py compare before.btf.gz after.btf.gz \
    --output compare.html --format html \
    --name-a "Before" --name-b "After"
```

#### Tickless vs tickful

Capture the **same workload** twice (tickless on / fixed tick), keep TICK STI enabled, and prefer matching busy windows (`--lo`/`--hi` or cursors).

| Compare signal | Why it matters |
|----------------|----------------|
| Tick mode / health / count | Confirms TICKLESS vs TICK |
| Context switches | Scheduler activity cost |
| Core gap avg/max, Load Balance | Idle/busy structure |
| Migrations | Whether tick policy changes bouncing |
| Execution / Blocking Max, p95 | Latency under each policy |

```bash
python builds/btf_viewer.py compare tracedata/tickless-8cores.zip \
    --output tick-policy-compare.html --format html \
    --name-a "Tickful" --name-b "Tickless" \
    --lo 1464000 --hi 1764000
```

| Observation | Typical reading |
|-------------|-----------------|
| Tickless: fewer ticks, higher CV; tickful: CV ≪ 5 % | Configurations captured correctly |
| Context switches ↓ on tickless in idle-heavy windows | Expected — suppressed idle ticks |
| Context switches similar on a fully busy phase | Tick policy has little effect when cores never idle |
| Blocking / Execution Max worse on one side | Prefer that policy only if Δ fits latency budgets |

Use tickless when idle power matters and scoped busy-window metrics stay within budget. Prefer tickful when Trace Health must stay GOOD or soft real-time slices cannot tolerate tick stretching.

### 5.3 Tags and intervals

```c
trace_tag_emit(0, (int)value);          /* tag0_event … tag7_event */
trace_interval_start(1); /* … */ trace_interval_stop(1);
```

Waveform rows plus **Tag Analysis** / **Interval Analysis** charts. Notes with `tid:{task_id}` pair intervals per task.

![tag0_event waveform](../images/memusage.png)

---

## 6. Export Results

| Output | How |
|--------|-----|
| Findings text | Analysis → **Save as text…** |
| Statistics CSV/HTML | Statistics → Export (default section order; cursor scope respected) |
| Perfetto JSON | **File → Export Perfetto…** / `perfetto` CLI |
| Timeline PNG/SVG | Shot / Save as SVG |
| Headless report | `report trace.btf --output out.html --format html` |

Typical Analysis triggers: load imbalance (Score < 70 % or σ > 30 %), WCET / blocking candidates, L/M/H priority pattern, thrashing (high Migr rate / Ping), hot lock-bounce pairs, tick not GOOD, sync Core bounce > 0.

```bash
python builds/btf_viewer.py info ../tracedata/example-8cores.btf.gz
python builds/btf_viewer.py report ../tracedata/example-8cores.btf.gz \
    --output report.html --format html
# --lo/--hi are raw #timeScale units (us for this sample), not nanoseconds
python builds/btf_viewer.py report ../tracedata/example-8cores.btf.gz \
    --output pi.html --format html --lo 3042000 --hi 3359000
python builds/btf_viewer.py migrations ../tracedata/example-8cores.btf.gz -o mig.csv
python builds/btf_viewer.py snapshot ../tracedata/example-8cores.btf.gz \
    -o migrate.svg --view timeline --view-mode core --task "CS[22]" \
    --lo 1805000 --hi 1865000
python builds/btf_viewer.py snapshot ../tracedata/example-8cores.btf.gz \
    -o dispatch.svg --view plot --metric dispatch --task "SR0[271]"
python builds/btf_viewer.py snapshot ../tracedata/example-8cores.btf.gz \
    -o switch.svg --view plot --metric switch_overhead --core Core_0
python builds/btf_viewer.py snapshot ../tracedata/example-8cores.btf.gz \
    -o concurrency.svg --view plot --metric concurrency --active-cores 4
python builds/btf_viewer.py perfetto ../tracedata/example-8cores.btf.gz -o trace.json
```

---

## 7. AI Assistant Flow

Use the right-panel **AI** tab after Analysis Findings exist. The assistant receives **structured findings for the current Statistics scope** (plus span / core count) — never the raw BTF stream. Full setup and troubleshooting: [README.md § AI Assistant](README.md#ai-assistant-ollama).

```text
① Load trace + open Statistics
② (Optional) Place cursors → Limit to cursor range
③ Toolbar Analysis / Statistics findings for that scope
④ AI tab → template or free-form Ask
⑤ Context = Analysis Findings (+ span, cores, scope)
⑥ Ollama /api/chat  →  reply (jump:TIME links → timeline)
⑦ Open the Statistics section the reply names; verify on the timeline
```

### 7.1 One-time setup

| Step | Desktop | Web |
|------|---------|-----|
| Install Ollama + model | `ollama serve` then `ollama pull phi4-mini:3.8b` | Same; for browser CORS use `OLLAMA_ORIGINS="*" ollama serve` |
| Configure | **Settings → AI** (URL, model, reply language, optional API key) | Same |
| Verify | **Test connection** | Same |
| Show panel | **View → Show AI Assistant** / Display settings | Display → AI Assistant panel |

Cloud models: local proxy (`minimax-m3:cloud` + `ollama signin`) or `https://ollama.com` + API key (model without `:cloud`).

### 7.2 Recommended ask order

Match the [top-down ladder](#2-top-down-analysis-ladder). Prefer templates first, then free-form follow-ups.

| Order | Template / ask | Then verify in UI |
|------:|----------------|-------------------|
| 1 | **Analysis Findings** or **Triage findings** | Open each named Statistics section |
| 2 | **Tick health** | Trace Health (TICK); scope a busy window if TICKLESS |
| 3 | **Core balance** | Core Utilisation → Concurrent Active / Switch Overhead |
| 4 | **WCET / hot CPU** | Top Tasks → Execution Max; click Max to jump |
| 5 | **Highest latency** | Blocking → Dispatch → Preemption Chain |
| 6 | **Migration thrash** | Migrations Rate/Ping; Core-Pair Bounce % |
| 7 | **Priority inversion** | Priority Inheritance L/M/H |
| 8 | **Deadline / budget** | After thresholds are set in Settings → Analysis |

**Reply language:** **Language…** on the AI bar (or Settings → AI → Reply language).

**Times in replies:** `jump:1805120` (trace `#timeScale` units). Click the link (Desktop + Web) to seek the timeline, then confirm with Statistics / cursors.

### 7.3 Scope the question

| Goal | Before Ask |
|------|------------|
| Full-trace triage | Leave **Limit to cursor range** off |
| One suite phase (e.g. thrash window) | Place two cursors, enable **Limit to cursor range**, re-open Analysis if needed, then Ask |
| Compare builds | Run Trace Compare first ([§5.2](#52-compare-two-builds)); AI still sees the *active* tab’s findings only |

Clear the log between unrelated questions (**Clear**). Use **Stop** if a probe hangs on first model load.

### 7.4 When not to trust the reply

- Findings are empty or scope is wrong — fix Statistics/cursors first.
- Demo / concatenated stress traces — scope to one phase before acting on advice.
- Tick not GOOD / TICKLESS — ask about tick health, then re-check derived latency in a busy window.
- Always open the Statistics section and timeline evidence; treat AI as a triage aid, not ground truth.

---

## Quick-Reference: Metric to Root Cause

| Observed symptom | Start here | Then check |
|-----------------|------------|------------|
| Unknown — triage first | Toolbar **Analysis** | Named Statistics sections in each finding |
| Need a narrative triage | Right-panel **AI** ([§7](#7-ai-assistant-flow)) | Templates → open named sections; click `jump:TIME` |
| Tick jitter / tickless | Trace Health (TICK) | Scope busy window; Execution Max |
| Tickless vs tickful trade-off | Trace Compare (Tick mode, Context switches) | Execution / Blocking on the same busy phase |
| SMP uneven load | Core Utilisation (Score / σ) | Concurrent Core Active; Migrations, Affinity |
| Rarely *N* cores busy together | Concurrent Core Active | Affinity, Top Tasks, worker count |
| High scheduler / switch cost | Kernel Switch Overhead | Core Time Breakdown (Gap %) |
| Task too slow on CPU | Execution Time (Max / p95) | Preemption Chain, Mutex |
| Task waits too long | Blocking Time | Preemption Chain, Mutex |
| Ready→run delay (resume / create) | Dispatch / Scheduling Latency | Blocking, Preemption; needs STI resume Name[id] |
| Priority inversion | Priority Inheritance | Mutex pairing, Blocking |
| Core thrashing | Core Migrations (**Rate**, **Ping**, Dwell) | Task lock-highlight + Load; Core-Pair / Heatmap |
| Lock-bounce migrations | Core-Pair (**Bounces**, **Bounce %**) | Heatmap **Bounce Only**; Mutex **Bounces** |
| Lock / queue issues | Mutex/Semaphore / Queue | Blocking, Migrations |
| Suspend/resume | Task Lifecycle (Susp/Res) | Timeline STI |
| Affinity wrong | Core Affinity | Lock-bounce table |
| Custom metric / region | Tag / Interval Analysis | Owning task Execution Time |
| Before/after change | Trace Compare | Same cursor phases on both tabs |
