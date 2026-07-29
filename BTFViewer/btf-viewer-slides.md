---
marp: true
theme: default
paginate: true
style: |
  section {
    font-size: 1rem;
    padding: 40px 50px;
  }
  section.title {
    background: linear-gradient(135deg, #0d2b4e 0%, #1a6eb5 100%);
    color: white;
    text-align: center;
    justify-content: center;
  }
  section.title h1 { color: white; font-size: 2.4rem; border: none; }
  section.title h2 { color: #a8d4f5; font-size: 1.3rem; font-weight: normal; border: none; }
  section.title p  { color: #c8e4f8; font-size: 0.95rem; }
  section.section-header {
    background: #1a6eb5;
    color: white;
    justify-content: center;
    text-align: center;
  }
  section.section-header h1 { color: white; font-size: 2rem; border: none; }
  section.section-header h2 { color: #cce3f8; font-size: 1.1rem; font-weight: normal; border: none; }
  h1 { color: #0d2b4e; font-size: 1.6rem; border-bottom: 3px solid #1a6eb5; padding-bottom: 0.2em; margin-bottom: 0.6em; }
  h2 { color: #1a6eb5; font-size: 1.2rem; margin-top: 0.8em; margin-bottom: 0.3em; }
  h3 { color: #2e86c1; font-size: 1rem; margin-top: 0.5em; margin-bottom: 0.2em; }
  code { background: #eef4fb; padding: 0.1em 0.35em; border-radius: 3px; font-size: 0.88em; color: #1a3a5c; }
  pre  { background: #eef4fb; border-left: 4px solid #1a6eb5; border-radius: 4px; font-size: 0.8em; }
  table { font-size: 0.82rem; border-collapse: collapse; width: 100%; }
  th { background: #1a6eb5; color: white; padding: 5px 10px; }
  td { padding: 4px 10px; border-bottom: 1px solid #dce8f5; }
  tr:nth-child(even) td { background: #f4f8fd; }
  blockquote { border-left: 4px solid #f0a500; background: #fffbf0; padding: 0.5em 1em; color: #5a4000; font-style: normal; }
  ul li { margin-bottom: 0.25em; }
  .pill { display: inline-block; background: #1a6eb5; color: white; border-radius: 12px; padding: 2px 10px; font-size: 0.8rem; font-weight: bold; }
  .pill-warn { background: #d97706; }
  .pill-ok { background: #16a34a; }
  .step { font-weight: bold; color: #1a6eb5; }
---

<!-- _class: title -->

# BTF Viewer

## RTOS Scheduler Performance Analysis

A top-down guide: from system-level overview to root-cause diagnosis

---

# Why Trace-Driven Analysis?

Real-time systems fail in subtle ways — a task that **almost** meets its deadline, cores that are **almost** balanced, a mutex that **occasionally** bounces across cores.

Static review and printf-debugging cannot reveal these patterns. Trace-driven analysis gives you **evidence**, not guesses.

## The Top-Down Framework

```
System Overview
    └── Core-Level Health          ← Is the workload distributed correctly?
            └── Task-Level Timing  ← Are tasks executing within their budgets?
                    └── Scheduling Latency   ← Why do tasks wait?
                            └── Concurrency Issues  ← Locks, priority, migrations
                                    └── Compliance & Regression  ← Deadlines, diffs, CI
```

Every level narrows the search space before you zoom in further.

---

<!-- _class: section-header -->

# Step 1
## System Overview — Orient Yourself

---

# Load the Trace & Get Oriented

```bash
python btf_viewer.py your-trace.btf
```

Or drag-and-drop onto the window / **File → Open** (`Ctrl+O`).

## First Things to Do

| # | Action | Why |
|---|--------|-----|
| 1 | Press `Ctrl+0` | Fit the entire trace on screen |
| 2 | Switch to **Core View** | See all cores at once — one row per core, expandable |
| 3 | Enable **CPU Load Graph** (toolbar **Load**) | Instant per-core utilisation bar chart below the timeline |
| 4 | Read the **status bar** | Task count, segment count, total trace span |
| 5 | Open **Statistics panel** | Summary, utilisation, and top tasks — no cursors needed |
| 6 | Check **Trace Health (TICK)** badge | Green = healthy tick; amber/red = jitter or missed ticks |

> **Core View first, Task View later.** On SMP traces, Core View immediately reveals which cores are busy and which are idle before you start looking for specific tasks.

---

# The BTF Viewer Interface

![w:900](../images/btfviewer.png)

*Core View with the **CPU Load Graph** enabled. The right panel shows **Statistics → Execution Time Per Slice** with a distribution chart opened.*

---

<!-- _class: section-header -->

# Step 2
## Core-Level Health — CPU Utilisation & Load Balance

---

# Is the Workload Distributed Correctly?

## What to Look For

Open **Statistics → Core Utilisation**. The **Load Balance Score** summarises the entire picture:

$$\text{Load Balance Score} = 100 \times (1 - \text{Gini coefficient})$$

| Score | Meaning | Badge |
|-------|---------|-------|
| 90–100 | Well-balanced, σ < 30 % | 🟢 Green |
| 60–89 | Moderate imbalance | 🟡 Amber |
| < 60 | Severe imbalance; one or few cores dominate | 🔴 Red |

## Escalation Path

| Symptom | Drill into |
|---------|-----------|
| One core > 90 %, others near-idle | **Core Affinity** — tasks may be pinned |
| All cores high but one persistently low | **Preemption Chain** + **Mutex/Semaphore** — a lock serialises work |
| IDLE% unexpectedly high everywhere | **Trace Health (TICK)** — tickless idle may be active |

---

<!-- _class: section-header -->

# Step 3
## Task-Level Timing — Execution Time & WCET

---

# How Long Do Tasks Actually Run?

## Reading Execution Time Distributions

Open **Statistics → Execution Time Per Slice** → click any task row.

The distribution chart has two layers:

- **Scatter plot** — each point is one slice; x = start time, y = duration.
  An isolated outlier far above the cluster is a WCET candidate.
- **Histogram + CDF overlay** — the blue CDF curve shows what fraction of slices finish within a given duration.

## Finding the WCET

1. Sort by **Max** column — click the cell link to zoom the timeline to that exact slice
2. Compare **Max** vs **p95**: if they diverge significantly, the worst case is a rare spike, not a systematic issue
3. Use **p95** (not Max) as the design-margin number when the max is an outlier

> If Max >> p95, suspect an external interrupt or OS overhead — not a deterministic execution path.

---

# Execution Time Distribution

![w:850](../images/stats/stats-exec-cs11.svg)

*Scatter (top): all slices over the trace span. Histogram (bottom): log-scaled duration axis when range spans > 1 order of magnitude. **p50** (green) and **p95** (orange) lines align with the right-axis CDF ticks.*

---

# Task Timing Relationships

![w:750](../images/statistics.png)

*For consecutive activations of a task:*
- **Execution Time** = on-CPU slice duration
- **Block Time** = off-CPU gap between the end of one slice and the start of the next (≡ Tracealyzer's *Response Time*)
- **Inter-Arrival Time** = Execution Time + Block Time = gap between successive slice starts

These three metrics are linked. Understanding which one is inflated tells you *where* to look next.

---

<!-- _class: section-header -->

# Step 4
## Scheduling Latency — Why Do Tasks Wait?

---

# Diagnosing High Blocking Time

Blocking Time = the off-CPU gap a task waits before being allowed back on-CPU.  
Open **Statistics → Blocking Time**, sort by **Max** or **p95**.

## Decision Tree

| Blocking pattern | Root cause | Next action |
|-----------------|-----------|-------------|
| ≈ tick period | Runnable but waiting for scheduler tick | Raise priority; check tickless config |
| Sporadic spikes correlated with one preemptor | Priority inversion or CPU hog | **Preemption Chain Analysis** |
| ≈ mutex hold time | Lock contention; victim waits for holder | **Mutex/Semaphore** — reduce critical-section length |
| Constant across time | Periodic design — expected | Verify with inter-arrival vs. deadline |

## Drill-Down Steps

1. Click a task row → **blocking-time distribution chart** (scatter clusters = repeated contention events)
2. Click **Max** link → jump to the worst off-CPU gap on the timeline
3. **Preemption Chain** table → find the dominant preemptor during that gap
4. Cross-reference with **Mutex/Semaphore** object pointer to confirm lock contention

---

# Blocking Time & Preemption Chain

<div style="display:grid;grid-template-columns:1fr 1fr;gap:1rem">

![](../images/stats/stats-block-cs11.svg)

![](../images/stats/stats-preempt-cs24-cs25.svg)

</div>

*Left: Blocking Time scatter — clusters at specific time positions reveal periodic contention windows.*
*Right: Preemption Chain — each point = one preemption overlap event; y-axis = how long the preemptor held the core during the victim's gap. Click any point to jump to that segment.*

---

<!-- _class: section-header -->

# Step 5
## Concurrency Issues — Priority Inversion, Migrations & Mutex Health

---

# Priority Inversion: The L/M/H Pattern

Classic priority inversion: a **Low-priority holder (L)** blocks a **High-priority waiter (H)** while **Medium-priority tasks (M)** run freely.

## Detecting It

Open **Statistics → Priority Inheritance** (visible only when `priority_inherit` / `priority_disinherit` STI events are present).

| Pattern column shows | Meaning |
|---------------------|---------|
| **Mutex inherit** | Kernel boosted holder — correct behaviour |
| **L/M/H pattern** | Inversion geometry detected — M ran while H waited |
| **Boost only** | Manual priority-set; no kernel inheritance involved |

## On the Timeline

Look for the **red bottom stripe** on the holder's task row — it marks the entire boost window from `priority_inherit` to `priority_disinherit`. Expand the core in Core View to see L (boosted), M (running), and H (blocked) simultaneously.

---

# Priority Inversion — Visual Evidence

![w:860](../images/stats/tasks-priority-il266.svg)

*Core View expanded to the boost window. The **red bottom stripe** on the low-priority holder's row marks the `priority_inherit` → `priority_disinherit` interval. During this window the kernel prevents M from preempting L.*

---

# Priority Boost Distribution Chart

![w:820](../images/stats/stats-priority-il266.svg)

*Red points = mutex-inherit episodes (kernel-managed); orange = manual priority boosts. The **Pattern** column classifies each episode. Click any point to zoom the timeline and annotate that exact episode.*

---

# SMP Core Migrations

Tasks that move between cores introduce cache-cold penalties and can cause lock-boundary races. Open **Statistics → Core Migrations**.

## Key Metrics

| Metric | What it means | Red flag threshold |
|--------|--------------|-------------------|
| **Rate** | Migrations per second of active time | High relative to execution frequency |
| **Dwell** | Average on-CPU slice before migrating | Very short dwell + high rate = ping-pong |
| **Ping-pong** | A→B followed immediately by B→A | Any non-zero count warrants inspection |
| **Lock-bounce %** | Migrations where mutex was held | > 5 % is a correctness risk on SMP |

## Migration Heatmap (toolbar **Heatmap**)

- **Level 1**: directed core-pair rows × 32 time bins — dark cell = migration burst
- **Click** a hot cell → **Level 2**: per-task sub-bins within that pair/window
- **Click** a task cell → zoom timeline, place cursors, switch to Task View, filter to that task

---

# Migration Heatmap — Two-Level Drill-Down

<div style="display:grid;grid-template-columns:1fr 1fr;gap:1rem">

![](../images/heatmap-pairs.svg)

![](../images/heatmap-tasks.svg)

</div>

*Left — Level 1: directed core-pair rows × 32 time bins. Darker = more migrations.*
*Right — Level 2: per-task sub-bins after clicking a hot cell. Click a task cell to zoom the timeline and filter to that task.*

---

# Mutex & Semaphore Correctness

Open **Statistics → Mutex / Semaphore pairing**. Each sync object is identified by its unique pointer.

## Pairing Issues Table

| Issue | Meaning | Risk |
|-------|---------|------|
| **Orphan give** | `give` with no matching `take` | Double-release bug |
| **Cross-task give** | `give` by different task than `take` | Valid for binary semaphores; bug for mutexes |
| **Unmatched take** | `take` with no `give` at trace end | Leaked lock / deadlock risk |
| **CORE_MIGRATION_WHILE_HELD** | Task crossed core boundary holding the lock | Race condition on SMP |

Click any issue row → timeline zooms to that event, segment is highlighted, annotation is added.

## Core Bounce Investigation

High **Core bounce** on a mutex → cross-reference **Core-Pair Migration Summary** → zoom to that pair/window → decide if affinity pinning or critical-section restructuring helps.

---

<!-- _class: section-header -->

# Step 6
## Compliance & Regression — Deadlines, Scope, Compare & Export

---

# Verifying Deadlines & CPU Budgets

Configure thresholds once in **Settings** (`Ctrl+,`) → **Analysis thresholds**:

```
CPU budget %:   25          ← flag any task using > 25 % CPU
Task deadlines: Worker[0]=500000
                SensorTask[2]=250000   ← nanoseconds; one Name=ns per line
```

## Reading Violations

**Statistics → Deadlines / CPU budget**:

| Table | Shows |
|-------|-------|
| **Slice over deadline** | Every slice that exceeded its per-task threshold, sorted by excess |
| **CPU budget exceeded** | Tasks whose CPU% in the current scope exceeds the global limit |

Click any **Max** link in the violation table → jump directly to that slice on the timeline.

> Place cursors around a specific test phase and enable **Limit to cursor range** to validate compliance phase by phase, without noise from the rest of the trace.

---

# Scoping with Cursors

![w:820](../images/example.png)

*Three cursors C1, C2, C3 placed on the timeline. The Δ badges show elapsed time between consecutive cursors. Enable **Limit to cursor range (C1–Cn)** in Statistics to restrict all metrics to the C1–C3 window.*

## Cursor Scope Rules

| Metric | What counts as "inside" the range |
|--------|----------------------------------|
| Core & task CPU% | Overlapping active time ÷ range width |
| Execution / blocking time | Both slice endpoints **fully inside** |
| Inter-arrival | Activation **start** inside the range |
| Preemption chain | Victim gap and preemptor overlap both inside |

---

# Tick Health & Scheduler Timer

**Statistics → Trace Health (TICK)** — always check this before drawing timing conclusions.

| Symptom | Interpretation | Action |
|---------|---------------|--------|
| **TICKLESS** badge + large gaps | Low-power tickless mode active | Confirm it's intentionally enabled |
| Max tick period >> average | Missed tick — blocked by long critical section or ISR | Find the long slice in Execution Time |
| High CoV of tick intervals | Jitter — ISR latency or SMP scheduler interference | Investigate Preemption Chain on the tick task |
| Missed-tick estimate > 0 | Ring buffer saturated; events dropped | Increase ring buffer capacity |

Click **Tick Distribution…** for a histogram of tick intervals.

> A missed tick distorts *all* derived metrics (CPU%, blocking, inter-arrival). Resolve tick issues before trusting other numbers.

---

# Tick Distribution Chart

![w:820](../images/stats/stats-tick.svg)

*`example-8cores.btf`: 1966 TICK events, nominal 1.000 ms period (1000 Hz), CV ≈ 24.7 % → **TICKLESS**. Histogram peaks at 1×, 2×, 3× the nominal period show idle stretches skipping ticks; the largest gaps (up to 2.340 ms) are the 4 estimated missed ticks.*

---

# Build Comparison & Regression Testing

## GUI Workflow

1. Open both traces in separate tabs
2. **Statistics → Trace Compare…** — select Trace A and Trace B
3. Browse: **Summary · Top Tasks · Core Migrations · Blocking · Preemption · Sync**
4. The **Δ column** = B − A: negative blocking Δ = improvement; positive CPU Δ = regression

## Headless CLI — CI-Ready

```bash
# Before/after comparison
python btf_viewer.py compare before.btf after.btf \
    --output compare.html --format html \
    --name-a "v1.2" --name-b "v1.3"

# Full statistics report, scoped to a window
python btf_viewer.py report trace.btf \
    --output report.html --format html \
    --lo 100000 --hi 500000

# Core migration table as CSV
python btf_viewer.py migrations trace.btf -o migrations.csv
```

Headless commands exit **0** on success, **non-zero** on parse error — plug directly into CI pass/fail gates.

---

# Custom Observability — Tags & Intervals

## Tag Events — Scalar Metrics in the Trace

```c
trace_tag_emit(0, (int)xPortGetFreeHeapSize());   /* channel 0–7, 32-bit payload */
```

Appears as a **waveform row** in the timeline. Open **Statistics → Tag Analysis** for min/avg/max/p95 per channel.

![w:600](../images/memusage.png)

*`tag0_event` row expanded: heap bytes in use sampled on every RTOS tick. Drops = allocations freed; plateaus = steady-state consumption.*

## Interval Events — Code Region Timing

```c
trace_interval_start(1);   do_work();   trace_interval_stop(1);
```

Appears as **Interval N** bars in the timeline. **Statistics → Interval Analysis** gives min/avg/max/p95 and a distribution chart per interval ID.

---

<!-- _class: section-header -->

# Summary
## Symptom → Metric Quick Reference

---

# Symptom → Root Cause Map

| Observed symptom | Start here | Then check |
|-----------------|-----------|-----------|
| Task misses its deadline | **Execution Time** (WCET, p95) | Preemption Chain · Blocking · Priority Inheritance |
| Task waits too long between runs | **Blocking Time** (Max / p95) | Preemption Chain · Mutex/Semaphore · Inter-Arrival |
| SMP cores unevenly loaded | **Core Utilisation** (Load Balance Score) | Core Migrations · Core Affinity · Preemption Chain |
| Lock-related slowdown | **Mutex/Semaphore** (Issue count, Core bounce) | Blocking Time · Preemption Chain · Core Migrations |
| Priority inversion suspected | **Priority Inheritance** (L/M/H pattern) | Mutex/Semaphore pairing · Blocking Time |
| Tasks migrating excessively | **Core Migrations** (Rate, Ping-pong) | Migration Heatmap · Core Affinity violations |
| Tick irregularity / missed ticks | **Trace Health (TICK)** | Execution Time Per Slice (long slices blocking tick) |
| Memory or counter regression | **Tag Analysis** | Interval Analysis for the owning task |
| Code region too slow | **Interval Analysis** (WCET, p95) | Execution Time Per Slice for the owning task |

---

<!-- _class: title -->

# Start at the Top

## Work down the hierarchy — stop when you find the evidence

System → Core balance → Task timing → Latency → Concurrency → Compliance

&nbsp;

**Load a trace and open Statistics. Everything else follows.**

---

<!-- _class: title -->

# Demo
