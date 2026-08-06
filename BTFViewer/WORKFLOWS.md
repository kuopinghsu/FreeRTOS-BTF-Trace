# BTF Viewer — Application Notes

Top-down workflows for analysing RTOS scheduler behaviour with BTFViewer. Start at the system level, follow Analysis findings, then open the metric tables they name.

---

## Table of Contents

| Section | Purpose |
|---------|---------|
| [1. Load a trace](#1-load-a-trace) | Open a file and orient |
| [2. Top-down analysis ladder](#2-top-down-analysis-ladder) | Inspection order for any new trace |
| [3. Worked example — `example-8cores`](#3-worked-example--example-8cores) | Walkthrough with measured stats |
| [4. Deep-dive playbooks](#4-deep-dive-playbooks) | Procedures for specific metrics |
| [5. Scope, compare, and custom signals](#5-scope-compare-and-custom-signals) | Cursors, Trace Compare (tickless vs tickful), tags |
| [6. Export results](#6-export-results) | Findings, CSV/HTML, Perfetto, CLI |
| [Quick-reference](#quick-reference-metric-to-root-cause) | Symptom → metric map |

---

## 1. Load a Trace

```bash
python btf_viewer.py {tracefile}
```

**File → Open** (`Ctrl+O`) or drag-and-drop. Supported: `.btf`, `.btf.gz`, `.bz2`, `.zip`. On the web viewer, open `btf_viewer.html`.

![BTF Viewer — timeline with CPU Load graph and Statistics](../images/btfviewer.png)

*Timeline, CPU Load, and Statistics on first open.*

| Step | Action | Goal |
|------|--------|------|
| 1 | Status bar + `Ctrl+0` | Confirm span and counts; Fit to Window |
| 2 | Toolbar **Core** or **Task** + **Load** | Orient on cores or tasks; show CPU Load |
| 3 | **Statistics** + **Analysis** | Summary metrics and heuristic triage |
| 4 | **Trace Health (TICK)** | Confirm timer health before trusting derived timing |

For task-level migration analysis, see [§3.5](#35-concurrency--migrations-locks-priority-inheritance) and [§4.5](#45-core-migrations).

---

## 2. Top-Down Analysis Ladder

Work down this hierarchy. Stop when the evidence explains the symptom; do not open every Statistics section by default.

```text
① System health     Trace Health (TICK), span, instrumentation flags
② Core balance      Core Utilisation + Load Balance Score
③ Task CPU / WCET   Top Tasks → Execution Time Per Slice (Max)
④ Latency           Blocking Time → Preemption Chain
⑤ Concurrency       Core Migrations → Mutex/Semaphore → Priority Inheritance
⑥ Compliance        Deadlines / Affinity / Task Lifecycle / Tags / Intervals
```

**In the UI**

1. Open toolbar **Analysis** and read each finding.
2. Open the Statistics section named by the finding.
3. Click **Max**, scatter points, or heatmap cells to jump the timeline.
4. Place cursors (`C`) around the phase of interest and enable **Limit to cursor range**.

**Demo traces:** `example-8cores.btf.gz` concatenates intentional stress tests (context-switch thrash, mutex/queue storms, priority inversion, suspend/resume, affinity). A warning may be expected for that phase—scope to the phase before treating it as a product defect.

---

## 3. Worked Example — `example-8cores`

### 3.0 Trace snapshot

| Field | Value |
|-------|-------|
| File | `tracedata/example-8cores.btf.gz` |
| Span | **2.358 s** (`#timeScale us`) |
| Cores | **8** |
| Tasks / segments / STI | **154** / **31 141** / **33 495** |
| Context switches / migrations | **31 133** / **18 992** (138 migrated tasks) |
| Instrumentation | priority + sync + intervals |
| TICK | **WARNING / TICKLESS** — 2496 ticks, CV **35.9 %**, missed ≈ **8** |

Open **Statistics**, then **Analysis**. The HTML report Analysis card uses the same triage.

---

### 3.1 System health (TICK)

**Statistics → Trace Health (TICK)**

| Metric | Measured |
|--------|----------|
| Mode | **TICKLESS** (CV 35.9 % ≫ 5 % threshold) |
| Avg period | 944 µs (nominal 1.000 ms) |
| Max gap | 2.481 ms |
| Missed ticks (est.) | 8 large gaps |

![Tick interval distribution — example-8cores](../images/stats/stats-tick.svg)

*2496 TICK events; multi-tick gaps often fall in idle stretches between suite phases.*

**Interpretation.** Tickless idle is active. Large wall-clock gaps between ticks are not, by themselves, proof of a lost interrupt during busy work.

**Actions**

- Scope to a busy phase (for example CS stress) and re-check CV and large gaps.
- For tickful product configs, disable tickless, re-capture, and expect CV ≪ 5 %.
- Keep TICK STI enabled so Trace Health stays trustworthy.
- To quantify tickless vs tickful impact on context switches and latency, see [§5.2](#52-compare-two-builds).

---

### 3.2 Core balance

**Statistics → Core Utilisation**

| Core | CPU % (excl. IDLE/TICK) |
|------|-------------------------|
| Core_0 … Core_7 | 68.7, 59.9, 62.7, 65.1, 71.6, 74.0, 76.1, **77.3** |
| **Load Balance Score** | **95 %** (G = 0.049) |
| **σ** | **6.0 %** (OK; amber if σ > 30 %; red if Score &lt; 70 %) |

**Analysis:** cores look reasonably balanced (Score ≥ 85 % and σ ≤ 30 %).

**Interpretation.** SMP placement is healthy at system level. Imbalance is not the primary issue on this trace. Still check migrations—good balance can coexist with expensive bouncing.

---

### 3.3 Task CPU and WCET

**Top Tasks by CPU** (excl. IDLE/TICK) are the equal-priority context-switch workers `CS[11]`…`CS[28]`:

| Task | CPU % | Runs | Max slice | p95 |
|------|-------|------|-----------|-----|
| CS[28] | 15.9 % | 728 | **3.623 ms** | 1.631 ms |
| CS[11] | 15.3 % | 730 | 2.486 ms | 1.628 ms |
| CS[24] | 15.3 % | 727 | 3.283 ms | 1.644 ms |
| … | ~14–15 % each | ~700+ | ~2.5–3.5 ms | ~1.5 ms |

Also notable: `Med[267]` 6.0 % (priority-inversion medium task); `SM[*]` / `MX[*]` mutex/semaphore workers ~5–6 %.

**Procedure:** **Execution Time Per Slice** → sort by **Max** → click **Max** to zoom the WCET slice.

**Interpretation.** CPU is dominated by the CS stress cohort. Worst slices (~3–4 ms) are long relative to a 1 ms tick and can stretch ticks while those tasks run.

**Actions**

- Cap concurrency of equal-priority workers, or pin them with `vTaskCoreAffinitySet`.
- Set **Settings → Display → Analysis thresholds** deadlines (for example `CS[28]=2000000` for 2 ms — values are **nanoseconds**) and use **Statistics → Deadlines / CPU budget** (or click the section's **Settings → Display** link). Click a violating slice to annotate it on the timeline.
- On a long Max slice, check Preemption Chain and Mutex for lock hold or migration.

---

### 3.4 Latency (blocking / response time)

**Statistics → Blocking Time** (off-CPU gap = Tracealyzer-style response-time gap)

| Task | Gaps | Max block | Notes |
|------|------|-----------|-------|
| Med[267] | 1160 | **35.305 ms** | Medium task around inversion test |
| Low[266] | 725 | **39.718 ms** | Low holder; waits around boost windows |
| High[268] | 6 | **52.865 ms** | High waiter during inversion demo |
| CS[*] | ~700+ | ~5–6 ms | Contended equal-priority cohort |
| Runner[1] | 335 | 737 ms | Orchestrator sleep between tests — ignore |

**Analysis:** warning on blocking candidates (`Med[267]`, `CS[19]`, …).

**Interpretation.** Extreme High/Low/Med gaps are expected for test 8 (priority inversion). CS blocking ~5 ms reflects peer contention and migration.

**Actions**

- Scope cursors to the inversion window (`Low`/`Med`/`High` ≈ 3.085–3.310 s); ignore Runner sleeps.
- For product tasks with High-like latency, require mutex priority inheritance and measure Max block under load.
- Cross-check **Preemption Chain** (for example `CS[25]←CS[19]` 44× / 14 ms total).

---

### 3.5 Concurrency — migrations, locks, priority inheritance

#### Core migrations

**Analysis:** excessive bouncing / core thrashing on CS tasks.

| Task | Migrations | Rate | Avg dwell | Ping-pong | Cores |
|------|------------|------|-----------|-----------|-------|
| CS[18] | 586 | **1692 /s** · 1.41/tick | 476 µs | 24 | 8 |
| CS[21] | 580 | 1648 /s | 494 µs | 19 | 8 |
| CS[12] | 579 | 1615 /s | 494 µs | 23 | 8 |

Trace-wide: **18 992** migrations. Hottest core pairs (Core-Pair Summary): `Core_5→Core_7` (599), `Core_4→Core_6` (560), … — mostly **0 % lock-bounce**.

**Interpretation.** Expected result of test 1 (equal-priority CS storm). In a product, this pattern drives cache-cold penalties and run-queue churn.

##### Ping-pong

**Statistics → Core Migrations → Ping** counts hops **A→B→A** within **1 µs**.

| Signal | Meaning |
|--------|---------|
| High **Ping** + high **Rate** / short **Dwell** | Rapid A↔B thrashing |
| High **Migr**, low **Ping** | Spreads across cores without A↔B oscillation |
| Elevated **STI±** with **Ping** | Scheduler/sync STI near the bounce — check Mutex/Semaphore |

On this sample, top CS tasks show Ping ≈ 19–24, Rate ~1.6k/s, Dwell ~0.5 ms.

**Procedure**

1. Sort **Core Migrations** by **Ping** or Rate.
2. Click the row → **Rate** and **Dwell** charts.
3. Lock-highlight the task on the timeline (below).
4. Confirm thrashing flags in toolbar **Analysis**.

##### Lock-bounce

A **lock-bounce** is a migration while a mutex/semaphore/queue hold is still active.

| Location | Columns / controls |
|----------|--------------------|
| **Core-Pair Migration Summary** | **Count**, **Bounces**, **Bounce %**, **Avg Gap** per `From→To` |
| **Mutex / Semaphore** | **Bounces** per object |
| Heatmap / Chord | **Show: Bounce Only** |

On this sample, hottest CS pairs are mostly **0 % Bounce** (scheduling thrash). Queue `0x80021990` shows **858** sync-object bounces.

**Procedure**

1. Open **Core-Pair Migration Summary**; sort by **Bounce %** or **Bounces**.
2. Click a busy pair → **Gap** chart (orange = lock-bounce samples) / **Rate** for burst timing.
3. Busy pairs with Bounce % ≥ ~25 % → pin sharers or redesign lock ownership.
4. Use dialog **Open Heatmap** / **Open Chord** (or toolbar **Bounce Only**) to see when lock-bounces cluster.
5. Confirm the object in **Mutex / Semaphore → Bounces**.

##### Task View + per-core CPU Load

1. Toolbar **Task** + **Load**.
2. Click a thrashing task label (for example `CS[22]`) — other tasks gray out.
3. **CPU Load** shows one sparkline per core for that task only.
4. Optionally zoom with cursors or `--lo`/`--hi`, then open Migrations / Core-Pair / Heatmap / Chord.

![CS[22] highlighted in Task View with per-core CPU Load](../images/stats/tasks-cpu-load-cs22.svg)

*`CS[22]` locked in Task View. Neighbouring tasks are grayed; CPU Load shows that task’s share on Core_0…Core_7.*

**Actions**

- Pin latency-critical tasks; leave only best-effort work fully migratable.
- Prefer fewer runnable equals over more workers for throughput.
- After affinity changes, re-measure **Ping** and Migr rate.
- Use toolbar **Heatmap** (32 bins) to confirm migrations concentrate in the CS phase, then scope Statistics to that window.
- For lock-bounce: co-locate tasks that share a hot mutex/queue; verify with **Bounce Only**.

#### Mutex / semaphore / queue

| Object | Holds | Issues | Core bounces | Status |
|--------|-------|--------|--------------|--------|
| mutex `0x80021920` | 864 | 6 | 6 | Warning |
| queue `0x80021990` | 864 | 0 | **858** | OK status, extreme bounce |
| several sems | few | 1 each | 2–5 | Warning (unmatched / bounce) |

**Analysis:** 19 sync objects with Core bounce > 0; 6 migration-while-held issues.

**Actions**

- Tasks that share a hot mutex/queue should share an affinity mask.
- Investigate Warning rows (unmatched take/delete) on the timeline; demo teardown can leave unpaired STI.

#### Priority inheritance

| Task | Base→Peak | Boosts | Boosted time | Pattern |
|------|-----------|--------|--------------|---------|
| Low[266] | 2→4 | 3 | **103.318 ms** | **Mutex inherit** |
| PS[228] | 2→4 | 1 | 119 µs | **L/M/H pattern** |

![Priority inversion — red inherit stripes on Low](../images/stats/tasks-priority-low.svg)

*Three red bottom stripes on `Low[266]` during test 8 (`priority_inherit` → `priority_disinherit`).*

**Interpretation.** Kernel inheritance on `Low[266]` is working. `PS[228]` still shows L/M/H geometry—open that episode and confirm whether a medium task ran while a higher waiter blocked.

**Actions**

- Keep priority inheritance enabled for mutexes that can block higher priorities.
- Treat any **L/M/H** row as a design review (shorten critical sections, raise holder base priority, or split locks).
- Doc snapshot window: `--lo 3042000 --hi 3359000` (µs).

---

### 3.6 Compliance — affinity, suspend/resume, tags

#### Core affinity (test 10)

**Statistics → Core Affinity** — `Aff[287]`…`Aff[298]` masks `0x1`…`0x80` observed only on the matching core; `AffM[299]` changes `0x1 → 0x80` and appears on Core_0/3/7. **No violations.**

Use the same pattern for IO-bound or lock-sharing tasks; re-check after every affinity change.

#### Suspend / resume (test 9)

**Statistics → Task Lifecycle**

| Task | Susp/Res | Runs | Alive span |
|------|----------|------|------------|
| SR0[271] … SR3[274] | **4/4** each | 32–50 | ~13–15 ms |

Equal Susp/Res confirms STI lifecycle hooks. On the timeline, suspended subjects must not run between `suspend` and `resume`.

#### Tags / intervals

**Tag Analysis → `tag0_event`:** 2357 samples (min 8 144, avg ≈ 34 631, max 45 392, p95 41 936).

![tag0_event distribution](../images/stats/stats-tag0.svg)

Bind tag channels to real budgets (heap high-water, queue depth). Rising max/p95 across builds → Trace Compare on Tag / Interval Analysis.

---

### 3.7 Performance verdict and improvement plan

| Priority | Finding | On this sample | Product action |
|----------|---------|----------------|----------------|
| P0 | CS migration thrash (~1.6k/s, dwell ~0.5 ms) | Expected stress | Affinity-pin hot tasks; reduce equal-priority fan-out; re-measure Migr rate / Ping |
| P0 | Queue/mutex core bounces (queue **858**) | Stress + shared objects | Co-locate producers/consumers; shorten holds; consider core-local queues |
| P1 | Priority L/M/H on `PS[228]`; High Max block ~53 ms | Demo inversion | Keep inheritance; audit critical sections; set **Display → Analysis thresholds** |
| P1 | WCET CS Max ~3.6 ms vs 1 ms tick | Stress length | Budget slices; break work; verify under tickful config |
| P2 | TICKLESS CV 35.9 %, missed ≈ 8 | Idle between tests | Scope busy windows before chasing missed ticks |
| P2 | Load Balance 95 %, σ 6 % | Healthy | No balance change |
| OK | Affinity + SR Susp/Res 4/4 | Hooks correct | Keep as CI regression checks (`report` HTML) |

**Before/after capture**

```bash
python builds/btf_viewer.py compare before.btf.gz after.btf.gz \
    --output compare.html --format html \
    --name-a "Before" --name-b "After"
```

Success criteria in Δ: lower CS Migr rate / Ping, lower queue Bounces, stable or improved High Max block, Load Balance Score ≥ 85 % with σ ≤ 30 %.

---

## 4. Deep-Dive Playbooks

Use when Analysis or the ladder points at a specific metric. Examples assume `example-8cores` unless noted.

### 4.1 Core utilisation and load balance

1. **Statistics → Core Utilisation** — bars are active (non-IDLE, non-TICK) CPU%.
2. Badge amber when σ > 30 %.
3. **Analysis** warns when Score < 70 % or σ > 30 %; “reasonably balanced” when Score ≥ 85 % and σ ≤ 30 %.
4. **Top Tasks by CPU** — who consumes the budget.

| Symptom | Next |
|---------|------|
| One core > 90 %, others idle | **Core Affinity** |
| All high, one low | **Mutex/Semaphore**, **Preemption Chain** |
| Score mid (~60 %) but σ ≤ 30 % | Still uneven — **Core Migrations** |

### 4.2 WCET (execution time per slice)

1. **Execution Time Per Slice** → sort **Max**.
2. Click **Max** — zoom and annotate.
3. Check neighbours on the core and **Preemption Chain** for that victim.

### 4.3 Blocking / scheduling delay

1. **Blocking Time** → sort **Max** / **p95**.
2. Long gap → **Preemption Chain** and **Mutex/Semaphore**.
3. Scope away from orchestrator sleeps (`Runner`).

This is the off-CPU gap until the next resume, not release-to-completion
response time. True response time requires explicit release/completion events.

### 4.4 Priority inversion

1. **Priority Inheritance** (needs `priority_inherit` / `priority_disinherit` STI).
2. Patterns: **Mutex inherit**, **L/M/H**, **Boost only**.
3. Timeline: red bottom stripe on the holder for the boost window.
4. Distribution chart → click a point to jump.

### 4.5 Core migrations

1. **Core Migrations** — sort by **Rate**, **Dwell**, **Ping** (A→B→A within 1 µs). High Rate + short Dwell + high Ping → thrashing; open Rate / Dwell / Gap charts.
2. **Core-Pair Migration Summary** — **Bounces** / **Bounce %** = lock held across the hop. High Bounce % on a busy pair → pin sharers or redesign ownership.
3. **Task View** + lock-highlight + **Load** for per-core CPU Load of that task (`snapshot … --view-mode task --task … --cpu-load`; see §3.5).
4. Toolbar **Heatmap** / **Chord** — **Bounce Only** for lock-bounce; All Migrations for thrash timing.
5. **Mutex / Semaphore → Bounces** — object-level confirmation.
6. Red flags: high Rate + short Dwell + high Ping; elevated Bounce % on latency paths; one task’s load spread thinly across many cores.

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
3. Desktop: navigator minimap sits above the CPU Load overlay while zoomed.

### 4.9 Deadlines and CPU budgets

**Settings** (`Ctrl+,`) → **Display → Analysis thresholds**, or click **Settings → Display** inside **Statistics → Deadlines / CPU budget**:

| Threshold | Example |
|-----------|---------|
| CPU budget % | `25` |
| Task deadlines | `CS[28]=2000000` (**ns**) — slices longer than **2 ms** after conversion to the trace time unit |

Then expand **Deadlines / CPU budget**:

- **Slice over deadline** — top 20 by duration; click a header to sort; click a row to jump and annotate the over-limit slice.
- **CPU budget exceeded** — click a row to highlight the task; click headers to sort.
- Scope per test phase with cursors + **Limit to cursor range**.

Exports (**CSV** / **HTML**) include both violation tables when thresholds are configured.

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
2. Tabs: Summary (load balance + tick), Top Tasks, Core Util, Migrations, Execution, Blocking, Inter-Arrival, Preemption, Sync.
3. **Δ** = A − B. Export CSV/HTML.

```bash
python builds/btf_viewer.py compare before.btf.gz after.btf.gz \
    --output compare.html --format html \
    --name-a "Before" --name-b "After"
```

#### Use case: tickless vs tickful (context switch and performance)

Capture the **same workload** twice—once with FreeRTOS tickless idle enabled, once with a fixed tick—and compare scheduler cost and application latency.

**Capture**

1. Build A: tickless enabled (`configUSE_TICKLESS_IDLE`).
2. Build B: tickless disabled (fixed tick).
3. Run the same test suite and duration; keep TICK STI enabled on both.
4. Prefer matching wall-clock windows (or the same `--lo`/`--hi` phases) so Δ is not dominated by idle gaps between tests.

**Compare in the UI**

1. Open both traces as tabs.
2. Optionally place the same cursor window on each busy phase and enable **Limit to cursor range**.
3. Statistics footer → **Trace Compare…**.

**What to read**

| Compare tab / row | Why it matters |
|-------------------|----------------|
| Summary → **Tick mode** / **Tick health** / **Tick count** | Confirms TICKLESS vs TICK; tickful should show lower CV and stable period |
| Summary → **Context switches** | Scheduler activity cost between configs |
| Summary → **Core gap avg/max**, **Load Balance Score** / **σ** | Idle/busy structure and SMP balance |
| Summary → **Migrations** | Whether tick policy changes cross-core bouncing |
| **Execution** (Max / p95) | Slice WCET and CPU share shifts |
| **Blocking** (Max / p95) | Response-time impact under each tick policy |
| **Preemption** | Peer interference / tick-driven preemption differences |
| **Top Tasks** / **Core Util** | Who absorbs the tick or wake-up overhead |

**CLI**

```bash
# Pair zip (two .btf members) or two separate paths:
python builds/btf_viewer.py compare tracedata/tickless-8cores.zip \
    --output tick-policy-compare.html --format html \
    --name-a "Tickful" --name-b "Tickless"
python builds/btf_viewer.py compare tickless.btf.gz tickful.btf.gz \
    --output tick-policy-compare.html --format html \
    --name-a "Tickless" --name-b "Tickful"
# Optional: same busy phase in #timeScale units (us on example-8cores)
python builds/btf_viewer.py compare tracedata/tickless-8cores.zip \
    --output tick-policy-busy.html --format html \
    --name-a "Tickful" --name-b "Tickless" \
    --lo 1464000 --hi 1764000
```

**Interpretation**

| Observation | Typical reading |
|-------------|-----------------|
| Tickless: fewer ticks, TICKLESS mode, higher CV; tickful: TICK, CV ≪ 5 % | Configurations captured correctly |
| Context switches ↓ on tickless in idle-heavy windows | Expected — suppressed idle ticks reduce scheduler wake-ups |
| Context switches similar on a fully busy CS phase | Tick policy has little effect when cores never idle |
| Blocking / Execution Max worse on one side | Prefer that policy only if the Δ is acceptable for latency budgets |
| Migrations ↑ with one policy | Re-check affinity; tick wake pattern can change placement |

Use tickless when idle power matters and scoped busy-window metrics stay within budget. Prefer tickful when Trace Health must stay GOOD or when soft real-time slices cannot tolerate tick stretching.

### 5.3 Tags and intervals

```c
trace_tag_emit(0, (int)value);          /* tag0_event … tag7_event */
trace_interval_start(1); /* … */ trace_interval_stop(1);
```

- Waveform rows plus **Tag Analysis** / **Interval Analysis** charts.
- Notes with `tid:{task_id}` pair intervals per task.

![tag0_event waveform](../images/memusage.png)

---

## 6. Export Results

### Analysis Findings

Toolbar **Analysis** (or HTML report card). Typical triggers:

| Finding | Trigger |
|---------|---------|
| Load imbalance | Score < 70 % or σ > 30 % |
| Balanced (info) | Score ≥ 85 % and σ ≤ 30 % |
| WCET candidates | Highest CPU% tasks |
| Blocking | Many / long off-CPU gaps |
| Priority inversion | L/M/H pattern |
| Thrashing | High Migr rate / **Ping** / short dwell |
| Hot lock-bounce pairs | Core-Pair **Bounce %** high (≈ ≥ 25 % on busy pairs) |
| Tick | Not GOOD, or missed > 0 |
| Sync bounces | Mutex/Semaphore **Bounces** / Core bounce > 0 |

### GUI and CLI

| Output | How |
|--------|-----|
| Findings text | Analysis → **Save as text…** |
| Statistics CSV/HTML | Statistics → Export |
| Perfetto JSON | **File → Export Perfetto…** / `perfetto` CLI |
| Timeline PNG/SVG | Shot / Save as SVG |
| Headless report | `report trace.btf --output out.html --format html` |

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
python builds/btf_viewer.py perfetto ../tracedata/example-8cores.btf.gz -o trace.json
```

---

## Quick-Reference: Metric to Root Cause

| Observed symptom | Start here | Then check |
|-----------------|------------|------------|
| Unknown — triage first | Toolbar **Analysis** | Named Statistics sections in each finding |
| Tick jitter / tickless | Trace Health (TICK) | Scope busy window; Execution Max slices |
| Tickless vs tickful trade-off | Trace Compare (Tick mode, Context switches) | Execution / Blocking / Preemption on the same busy phase |
| SMP uneven load | Core Utilisation (Score / σ) | Migrations, Affinity |
| Task too slow on CPU | Execution Time (Max / p95) | Preemption Chain, Mutex |
| Task waits too long | Blocking Time | Preemption Chain, Mutex, Inter-Arrival |
| Priority inversion | Priority Inheritance | Mutex pairing, Blocking |
| Core thrashing | Core Migrations (**Rate**, **Ping**, Dwell) | Task View lock-highlight + per-core Load; Core-Pair / Heatmap / Chord |
| Lock-bounce migrations | Core-Pair (**Bounces**, **Bounce %**) → Gap/Rate chart | Heatmap/Chord **Bounce Only**; Mutex/Semaphore **Bounces**; Affinity |
| Lock / queue issues | Mutex/Semaphore / Queue | Blocking, Migrations |
| Suspend/resume | Task Lifecycle (Susp/Res) | Timeline STI; demo test 9 |
| Affinity wrong | Core Affinity | Lock-bounce table |
| Custom metric / region | Tag / Interval Analysis | Owning task Execution Time |
| Before/after change | Trace Compare | Same cursor phases on both tabs |
