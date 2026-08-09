# FreeRTOS-BTF-Trace

A lightweight, open-source framework for recording and visualising FreeRTOS task scheduling traces.
Trace output is produced in two industry-standard formats:

- **BTF (Best Trace Format)** — a CSV-based format designed for system-level timing and performance analysis of embedded real-time systems. Specification available [here](https://assets.vector.com/cms/content/products/TA_Tool_Suite/Docs/BTF_Specification.pdf).
- **VCD (Value Change Dump)** — an ASCII-based waveform format compatible with logic simulation tools such as [GTKWave](http://gtkwave.sourceforge.net).

## Screenshot

![BTF Viewer screenshot](images/btfviewer.png)

[DEMO](https://apps.kuoping.com/btf_viewer.html?demo)

---

## Table of contents

| Section | For |
|---------|-----|
| [Overview](#overview) | What this project does and the trace pipeline |
| [Repository structure](#repository-structure) | Top-level directories |
| [Quick start](#quick-start) | Build the RV64 demo and generate `trace.btf` |
| [Demo](#demo) | SMP stress tests included in the repo |
| [Visualising traces](#visualising-traces) | BTF Viewer, Trace Compass, GTKWave |
| [Use cases](#use-cases) | Heap tags, intervals, migration heatmap |
| [Porting guide](#porting-guide) | Integrate into your FreeRTOS project |
| [Reference](#reference) | `trace.bin` layout, event → BTF mapping, RAM sizing |
| [Known limitations](#known-limitations) | Current gaps and caveats |

---

## Overview

Identifying performance bottlenecks in real-time embedded systems often requires a full-featured commercial tool such as [Percepio Tracealyzer](https://percepio.com/tracealyzer/). This project provides a simple, extensible, and completely free alternative: instrument FreeRTOS with trace hooks, capture context-switch events into a compact in-memory buffer, and convert that buffer to BTF or VCD for offline analysis.

A related approach using [BareCTF](https://barectf.org/) and [Eclipse Trace Compass](https://www.eclipse.org/tracecompass/) is available at [freertos-barectf](https://github.com/gpollo/freertos-barectf).

### Trace pipeline

```
FreeRTOS trace hooks
  → btf_trace_add_*() (ring buffer in RAM)
  → traceEND() writes trace.bin via fopen/fwrite/fclose
  → tools/gentrace
  → .btf / .vcd
  → BTFViewer (desktop or web) / Trace Compass / GTKWave
```

## Repository structure

```
FreeRTOS-Trace/   Trace library (hooks, ring buffer, file dump via fopen)
tools/            gentrace — binary dump → BTF or VCD
sim/              RV64 SMP instruction-set simulator (C++, supports --cores N)
Demo/             FreeRTOS SMP demo built for RV64, run under sim/
BTFViewer/        Interactive BTF viewer (PySide6 desktop + Vue 3 web app)
tracedata/        Sample outputs (example*.btf.gz, example.vcd)
images/           Documentation screenshots (timeline, stats plots, migration heatmaps)
```

---

## Quick start

### Prerequisites

The demo targets **RISC-V RV64** and runs on the included **`sim/`** simulator (a custom C++ RV64 ISS that supports SMP via `--cores N`).

Install the [xPack RISC-V Embedded GCC](https://github.com/xpack-dev-tools/riscv-none-elf-gcc-xpack) toolchain.  The default path expected by the build system is:

```
/opt/xpack-riscv-none-elf-gcc-15.2.0-1/bin/riscv-none-elf-gcc
```

Override with `RISCV_PREFIX` if yours is installed elsewhere:

```bash
make run RISCV_PREFIX=/path/to/riscv-none-elf-
```

### Build and Run

```bash
# Single-core (default)
make run

# SMP — 2 cores
make CORES=2 run

# SMP — 8 cores
make CORES=8 run
```

On the first run, `FreeRTOS-Kernel` (V11.3.0) is cloned automatically.
The build produces:

- `build/demo/examples/cores<N>/freertos_test.elf` — the FreeRTOS test binary
- `build/sim/riscv64-sim` — the RV64 simulator
- `build/tools/gentrace` — the trace converter

After the simulator exits it writes `trace.bin`; `gentrace` converts it to `tracedata/trace.btf` and `tracedata/trace.vcd`.

**View the trace:**

```bash
pip install -r BTFViewer/requirements.txt
python BTFViewer/builds/btf_viewer.py tracedata/trace.btf
```

Sample traces (gzipped BTF; Desktop and Web open `.btf` / `.btf.gz` / `.bz2` / `.zip` the same way): `tracedata/example.btf.gz`, `tracedata/example-2cores.btf.gz`, `tracedata/example-4cores.btf.gz` (SMP demos), `tracedata/example-8cores.btf.gz`, `tracedata/example-16cores.btf.gz` (large). Full viewer docs: [`BTFViewer/README.md`](BTFViewer/README.md).

---

## Demo

The demo (`Demo/examples/freertos_test/`) runs ten SMP stress tests:

| # | Test | What it exercises |
|---|------|-------------------|
| 1 | Context-switch stress | Rapid voluntary yields across all cores |
| 2 | Mutex contention | Priority-inheritance mutex under load |
| 3 | Counting semaphore + mutex | Mixed synchronisation primitives |
| 4 | Task notifications | Direct-to-task notification API |
| 5 | Event groups | Multi-bit event synchronisation |
| 6 | Queue stress | Producer/consumer queues at speed |
| 7 | Task priority set | `vTaskPrioritySet()` and `traceTASK_PRIORITY_SET` |
| 8 | Priority inversion | Classic L/M/H on one core (`Low` / `Med` / `High`), repeated 3× (`T8_ROUNDS`) |
| 9 | Task suspend/resume | Multi-subject `vTaskSuspend()` / `vTaskResume()`: suspend-while-blocked + suspend-while-running, overlapping across up to 4 cores (`T9_SUBJECTS`×`T9_ROUNDS`) |
| 10 | Core affinity | SMP only: pin / migrate with `vTaskCoreAffinitySet` (no-op pass on 1 core) |

Expected output (CORES=2 example):

```
freertos_test: starting
  cores=2   workers=6    sem_slots=2   iter_fast=24   iter_slow=12  t1_yields=3
test 1: context-switch stress       ... pass
test 2: mutex contention            ... pass
test 3: counting-sem + mutex        ... pass
test 4: task notifications          ... pass
test 5: event group                 ... pass
test 6: queue stress                ... pass
test 7: task priority set           ... pass
test 8: priority inversion          ... pass
test 9: task suspend/resume         ... pass
test 10: core affinity              ... pass
…
freertos_test: all tests passed
```

## Use cases

Worked examples from the demo firmware and BTFViewer. Detailed viewer workflows: [`BTFViewer/WORKFLOWS.md`](BTFViewer/WORKFLOWS.md) · user guide: [`BTFViewer/README.md`](BTFViewer/README.md).

### Use case: monitor heap usage with the tick hook

The demo records **heap bytes in use** on every RTOS tick and plots them in BTFViewer as an analog waveform.

**Setup (already enabled in this repo):**

| Item | Where | Setting |
|------|-------|---------|
| Heap allocator | `Demo/examples/Makefile` | `heap_4.c` (coalescing heap; exposes `xPortGetFreeHeapSize()`) |
| Tick hook | `Demo/conf/FreeRTOSConfig.h` | `configUSE_TICK_HOOK` = `1` |
| Tag events | `FreeRTOS-Trace/FreeRTOS-Trace.h` | `configINCLUDE_TAGS` = `1` (default) |
| Sampling code | `Demo/examples/freertos_test/main.c` | `vApplicationTickHook()` |

**What the hook does:**

```c
void vApplicationTickHook( void )
{
#if configUSE_TRACE_FACILITY
    size_t allocated = configTOTAL_HEAP_SIZE - xPortGetFreeHeapSize();
    btf_traceTAG( 0, (int) allocated );   /* STI tag0_event in the trace */
#endif
}
```

Each call emits a BTF line like:

```
1234567,Core_0,0,STI,tag0_event,0,trigger,4096
```

The last field is **bytes allocated** from the heap_4 pool at that tick.

**Run and view:**

```bash
make run
python BTFViewer/builds/btf_viewer.py tracedata/trace.btf
```

In BTFViewer, locate the **tag0_event** STI row in the label column and expand it to show the heap-usage waveform over time. Tags `1`–`7` (`btf_traceTAG( 1 … 7, value )`) are available for other periodic signals (stack high-water, custom counters, etc.).

![Memory Usage](images/memusage.png)

### Use case: measure code execution intervals

Pair **`interval_start` / `interval_stop`** STI events to bracket a region of code and record when it ran and how long it took. The demo wraps each stress test (and each test iteration) with these calls.

**Setup:** same as tag events — `configUSE_TRACE_FACILITY` = `1` and `configINCLUDE_TAGS` = `1` (default in `FreeRTOS-Trace/FreeRTOS-Trace.h`).

| API | Context | Description |
|-----|---------|-------------|
| `traceINTERVAL_START( id )` | Task | Record interval *start*; `id` is a user-defined integer (0 … 2³²−1) |
| `traceINTERVAL_STOP( id )`  | Task | Record interval *stop* for the same `id` |
| `btf_traceINTERVAL_START( id )` | Any* | Low-level start (no critical-section wrapper) |
| `btf_traceINTERVAL_STOP( id )`  | Any* | Low-level stop (no critical-section wrapper) |

\*Prefer the `traceINTERVAL_*` macros in task code. Use the `btf_traceINTERVAL_*` functions only when you already hold the trace lock or are in a context where the macro wrappers are unsuitable.

The logger records the **calling task id** automatically (`param2` in the binary event); you only pass the interval `id`.

**Example:**

```c
#if configUSE_TRACE_FACILITY
    traceINTERVAL_START( 1 );
#endif
    do_work();
#if configUSE_TRACE_FACILITY
    traceINTERVAL_STOP( 1 );
#endif
```

**Binary layout** — see [Binary → BTF dump mapping](#binary--btf-dump-mapping) (`param1` = interval `id`, `param2` = caller task id).

**BTF text** (from `gentrace` or live `btf_dump`): channel `interval_start` or `interval_stop`; the note field (last CSV column) is `{id} tid:{task_id}`:

```
214276,Core_0,0,STI,interval_start,0,trigger,0 tid:1
215514,Core_0,0,STI,interval_start,0,trigger,1 tid:7
217432,Core_1,0,STI,interval_stop,0,trigger,1 tid:7
```

In the demo (`Demo/examples/freertos_test/main.c`), `id` **0** brackets an entire test function; **1**–**9** bracket the inner loop of tests 1–9 respectively.

**In BTFViewer:** paired spans appear as **Interval N** rows at the bottom of the timeline (horizontal task view). When the BTF note includes `tid:{task_id}`, start/stop events pair by **interval id + task id**; legacy traces without `tid` pair by the note string alone. Open **Statistics → Interval Analysis** for duration summaries and charts. See the [BTFViewer user guide](BTFViewer/README.md#analysis) and [WORKFLOWS.md](BTFViewer/WORKFLOWS.md).

### Use case: SMP migration inspector

On multi-core traces, BTFViewer detects when the same task runs on different cores and exposes **Core Migrations** in the Statistics panel plus the **Migration & Corridor Inspector** (toolbar **Heatmap** / **Chord**). The inspector shows *where* traffic flows (mini-chord), *when* it bursts (time-bin grid), and *which tasks* drive it (expandable corridor tree) — complementary to the per-task migration table (ping-pong count, STI correlation, gap-after vs other gaps).

Open the 8-core sample and the inspector:

```bash
python BTFViewer/builds/btf_viewer.py tracedata/example-8cores.btf.gz
```

![Migration & Corridor Inspector](images/migration.svg)

Toolbar **Heatmap** / **Chord** opens tree + time grid + mini-chord. See [Migration & Corridor Inspector](BTFViewer/README.md#migration--corridor-inspector) and [WORKFLOWS.md](BTFViewer/WORKFLOWS.md).

---

## Visualising traces

### BTF Viewer (built-in)

An interactive Gantt-style viewer is included in the `BTFViewer/` directory (desktop app and browser build). Both support task/core timelines, cursors, statistics, Analysis Findings, migration tools, Trace Compare, AI Assistant, and export (PNG/SVG, Perfetto, CSV/HTML).

**Desktop requirements:** Python 3.8+ and PySide6 ≥ 6.4

```bash
pip install -r BTFViewer/requirements.txt
python BTFViewer/builds/btf_viewer.py tracedata/trace.btf
# or a compressed sample (Desktop + Web open .btf.gz the same way):
python BTFViewer/builds/btf_viewer.py tracedata/example-4cores.btf.gz
```

User guide: [`BTFViewer/README.md`](BTFViewer/README.md) · diagnosis walkthroughs: [`BTFViewer/WORKFLOWS.md`](BTFViewer/WORKFLOWS.md).

### Eclipse Trace Compass

Open `tracedata/trace.btf` directly in [Trace Compass](https://www.eclipse.org/tracecompass/).

![Trace Compass](images/trace-compass.png)

### GTKWave / VCD Viewer

```bash
gtkwave tracedata/trace.vcd
```

![VCD](images/vcd.png)

---

## Porting guide

Follow these steps to integrate the trace library into your own FreeRTOS project.

### 1. Include the trace header

Add the following line to your `FreeRTOSConfig.h`:

```c
#include "FreeRTOS-Trace/FreeRTOS-Trace.h"
```

Enable tracing in config:

```c
#define configUSE_TRACE_FACILITY  1
#define configMAX_TRACE_EVENTS    4096   /* adjust for RAM budget */
#define configMAX_TRACE_TASKS     64
```

### 2. Implement the time source

Edit `FreeRTOS-Trace/btf_port.h` and define the `xGetCycles()` macro to return the current system cycle counter:

```c
#define xGetCycles()  /* your platform timer, e.g. DWT cycle counter */
```

The RISC-V port uses `portGET_RUN_TIME_COUNTER_VALUE()` which maps to `rdcycle`.

### 3. Choose dump mode

| Mode | Configuration |
|------|---------------|
| **File dump** (default) | `HAVE_FILE_DUMP` in `btf_port.h` — writes `trace.bin` via `fopen`/`fwrite`/`fclose` at `traceEND()` |
| **Live stdout BTF** | Uncomment `#define PRINT_BTF_DUMP` in `btf_port.h` |
| **Buffer only** | Define neither — keep events in RAM and dump the `trace_data` symbol after the run via debugger/JTAG |

### 4. Add the source file to your build

Compile `FreeRTOS-Trace/btf_trace.c` as part of your project.

### 5. Start and stop tracing

```c
int main(void)
{
#if configUSE_TRACE_FACILITY
    traceSTART();
#endif

    xTaskCreate( ... );
    vTaskStartScheduler();
}

/* Inside the task that finishes last: */
#if configUSE_TRACE_FACILITY
    traceEND();   /* writes trace.bin */
#endif
exit(0);
```

### 5a. Custom instrumentation (tags & intervals)

When `configINCLUDE_TAGS` is `1`, you can emit user-defined STI events from application code:

| Macro | Underlying function | Purpose |
|-------|---------------------|---------|
| `traceTAG( t, v )` | `btf_traceTAG()` | Periodic sample; `t` = 0…7, `v` = 32-bit payload |
| `traceINTERVAL_START( id )` | `btf_traceINTERVAL_START()` | Mark the start of a timed code region (`param1` = `id`, `param2` = caller task id) |
| `traceINTERVAL_STOP( id )` | `btf_traceINTERVAL_STOP()` | Mark the end of the same region (`id` must match; same task id recorded in `param2`) |

See [Use case: monitor heap usage with the tick hook](#use-case-monitor-heap-usage-with-the-tick-hook) and [Use case: measure code execution intervals](#use-case-measure-code-execution-intervals) for worked examples.

### 6. SMP considerations

All trace hooks in `FreeRTOS-Trace/FreeRTOS-Trace.h` are protected by either `taskENTER_CRITICAL()` (task context) or `taskENTER_CRITICAL_FROM_ISR()` (ISR / context-switch context).

The RISC-V SMP port (`Demo/port/RISC-V/port.c`) implements both the task lock and the ISR lock as **recursive** spinlocks (owner + count).  This allows `traceTASK_SWITCHED_OUT/IN` — which fire inside `vTaskSwitchContext` while the ISR lock is already held — to safely re-enter the same lock without deadlocking.

**Core affinity tracing** — to record `vTaskCoreAffinitySet()` calls so BTFViewer can show the **Core Affinity** statistics table, enable `configUSE_CORE_AFFINITY` = `1` (SMP builds), `configINCLUDE_SCHEDULING` = `1` (the default), and include `FreeRTOS-Trace/FreeRTOS-Trace.h`. FreeRTOS V11 fires `traceENTER_vTaskCoreAffinitySet` (not a `traceTASK_CORE_AFFINITY_SET` macro); the BTF layer hooks that ENTER point and records the bitmask as an STI event (`affinity_set Name[id] 0xMASK` on the `task` channel). BTFViewer parses this and cross-checks observed execution cores against the mask to flag violations.

### 7. Convert to BTF or VCD

```bash
# BTF format
tools/gentrace trace.bin trace.btf

# VCD format
tools/gentrace -v trace.bin trace.vcd
```

Event-to-BTF field mapping is documented in [Binary → BTF dump mapping](#binary--btf-dump-mapping). Optional [BTF quality metadata](#btf-quality-metadata) lines report ring overflow, task-table overflow, or truncation. The input file layout is in [`trace.bin` binary format](#tracebin-binary-format).

### 8. Open the trace

- **BTF:** open with `BTFViewer/builds/btf_viewer.py`, the web viewer, or Eclipse Trace Compass.
- **VCD:** open with GTKWave or any compatible VCD viewer.

---

## Reference

On-disk `trace.bin` layout, event encoding, BTF quality metadata, and BTF line generation. For viewer usage (task labels, STI, intervals on the timeline), see the [BTFViewer user guide](BTFViewer/README.md).

### `trace.bin` binary format

At `traceEND()`, the firmware writes a single little-endian blob (`fwrite` of the in-RAM `TRACE` structure in `btf_trace.h`). `tools/gentrace` reads this file and converts it to BTF or VCD. The on-disk layout is:

```
┌─────────────────────────────────────────────────────────────┐
│ TRACE_HEADER  (44 bytes)                                    │
├─────────────────────────────────────────────────────────────┤
│ task_lists[max_tasks × max_taskname_len]  (NUL-terminated   │
│   task name per task id slot; index = uxTCBNumber)          │
├─────────────────────────────────────────────────────────────┤
│ event_lists[max_events]  (ring buffer of EVENT records)     │
└─────────────────────────────────────────────────────────────┘
```

**File size** (bytes):

```
44 + max_tasks × max_taskname_len + max_events × 16
```

`max_tasks`, `max_taskname_len`, and `max_events` come from the header (set at `traceSTART()` from `configMAX_TRACE_TASKS`, `ALIGN4(configMAX_TRACE_TASK_NAME_LEN+1)`, and `configMAX_TRACE_EVENTS`). The demo build passes `MAX_TRACE_EVENTS` on the Makefile command line (default 400000).

#### `TRACE_HEADER` (44 bytes, little-endian)

| Offset | Field | Type | Description |
|--------|-------|------|-------------|
| 0 | `header` | `char[4]` | Magic `B` `T` `F` `2` |
| 4 | `tag` | `uint32_t` | Endian marker — must be `1` (little-endian) |
| 8 | `version` | `uint32_t` | `TRACE_VERSION` = `(major<<16)\|minor` (currently **1.4** → `0x00010004`) |
| 12 | `core_clock` | `uint32_t` | CPU frequency (Hz); used to convert timestamps to BTF time |
| 16 | `num_cores` | `uint32_t` | `configNUMBER_OF_CORES` |
| 20 | `max_tasks` | `uint32_t` | Task name table slots |
| 24 | `max_taskname_len` | `uint32_t` | Bytes per task name slot (4-byte aligned) |
| 28 | `max_events` | `uint32_t` | Ring buffer capacity |
| 32 | `task_count` | `uint32_t` | Number of `TASK_CREATE` events recorded |
| 36 | `event_count` | `uint32_t` | Events in buffer (≤ `max_events`; stops growing after wrap) |
| 40 | `current_index` | `uint32_t` | Next write index; also start of oldest event when full |

#### Task name table

- `task_lists[task_id][0 … max_taskname_len-1]` — C string, max `configMAX_TRACE_TASK_NAME_LEN` characters plus NUL.
- Slot index is the FreeRTOS **task id** (`uxTCBNumber`), not a dense 0…N−1 index.
- Written by `btf_trace_add_task()` on `traceTASK_CREATE`. If `task_id` is `0` or ≥ `configMAX_TRACE_TASKS`, the name is not stored but the event is still recorded and `#taskTableOverflow true` is emitted at export.

#### `EVENT` record (16 bytes)

| Offset | Field | Type | Description |
|--------|-------|------|-------------|
| 0 | `timestamp` | `uint32_t` | Raw counter from `xGetCycles()` (may wrap at 2³²; extended offline) |
| 4 | `param1` | `uint32_t` | Event-specific (see [dump mapping](#binary--btf-dump-mapping)) |
| 8 | `param2` | `uint32_t` | Event-specific |
| 12 | `types` | `uint32_t` | Event type + optional core id (SMP) |

**`types` field:**

| Bits | Meaning |
|------|---------|
| `[23:0]` | `event_t` value (see `btf_trace.h`) |
| `[30:24]` | Core id when `num_cores` > 1 (from `portGET_CORE_ID()` at record time) |
| `[31]` | Unused (mask is `0x7f000000` for core) |

On single-core builds, the full `types` word is just the `event_t` enum value (core bits zero).

**`event_t` values:**

| Value | Symbol |
|------:|--------|
| 1–7 | `TASK_SWITCHED_IN` … `TASK_RESUME_FROM_ISR` |
| 8–11 | `QUEUE_CREATE` … `QUEUE_DELETE` |
| 12 | `TASK_INCREMENT_TICK` |
| 13–14 | `INTERVAL_START`, `INTERVAL_STOP` |
| 15 | `TASK_PRIORITY_SET` |
| 16 | `TASK_PRIORITY_INHERIT` |
| 17 | `TASK_PRIORITY_DISINHERIT` |
| 18 | `TASK_SET_AFFINITY` |
| 90–97 | `TAG` … `TAG7` |

#### Ring buffer iteration

Events are appended at `current_index` (mod `max_events`). When `event_count == max_events`, the buffer has wrapped: `gentrace` / `btf_dump` replay from `current_index` (oldest) through `current_index - 1` (modulo). When not full, replay starts at index `0`.

After the ring is full, new events **overwrite** the oldest slots; `event_count` stays at `max_events`. Firmware prints a one-time warning: *only last events will be recorded*. When the BTF file is exported, `#ringOverflow true` is written — see [BTF quality metadata](#btf-quality-metadata).

#### Timestamps

`timestamp` is a free-running **32-bit** counter (platform-defined via `xGetCycles()` in `btf_port.h`). `gentrace` and `btf_dump()` detect wrap and build monotonic 64-bit times scaled by `core_clock` (microseconds or nanoseconds in the output BTF file).

#### BTF quality metadata

After the standard header lines (`#version`, `#creator`, `#creationDate`, `#timeScale`), `tools/gentrace` and live `btf_dump()` may emit optional integrity flags as `#key value` pairs. Lines are omitted when the condition is false (a clean trace has no quality meta).

| Meta line | Meaning | How it is detected |
|-----------|---------|---------------------|
| `#ringOverflow true` | Event ring buffer wrapped; oldest events may be missing | `event_count == max_events`, or firmware saw a wrap while recording |
| `#taskTableOverflow true` | Task name table could not record a task id | Invalid `task_id` (`0` or ≥ `max_tasks`), or events reference a task id with no stored name |
| `#truncated true` | Trace did not finish normally | Firmware: `btf_traceEND()` was not called before dump. `gentrace`: input file is smaller than a full `TRACE` blob |

Example (ring overflow on a long capture):

```
#version 2.2.0
#creator FreeRTOS trace logger
#creationDate 2026-06-20T08:33:13Z
#timeScale us
#ringOverflow true
213463,Core_0,0,C,Core_0,0,set_frequency,20000000
…
```

These flags are **inferred at BTF export time** from runtime state and buffer contents. They are not stored in the `TRACE_HEADER` binary layout, so existing `trace.bin` files stay compatible.

BTFViewer (desktop and web) reads `#ringOverflow`, `#taskTableOverflow`, and `#truncated` from the parsed meta dict and shows a banner at the top of the timeline when any flag is set.

---

### Binary → BTF dump mapping

`tools/gentrace` and live `btf_dump()` (`PRINT_BTF_DUMP` in `btf_port.h`) use the same rules to turn each `trace.bin` event into one BTF CSV line:

`time, source, 0, type, target, 0, action, note`

On SMP (`configNUMBER_OF_CORES` > 1), the emitting core is stored in the high bits of `event.types` and appears as `source` (`Core_N` or `[N/…]` in task rows). `param1` / `param2` are the 32-bit fields in the `EVENT` struct (`btf_trace.h`).

| Event (`event_t`) | Hook / API | `param1` | `param2` | BTF `type` | BTF `target` | BTF `action` | BTF `note` (last field) |
|-------------------|------------|----------|----------|------------|--------------|--------------|-------------------------|
| `TASK_SWITCHED_IN` (1) | `traceTASK_SWITCHED_IN` | task id | 0 | `T` | `[core/id]Name` | `resume` | *(empty)* |
| `TASK_SWITCHED_OUT` (2) | `traceTASK_SWITCHED_OUT` | task id | 0 | `T` | `[core/id]Name` | `preempt` | *(empty)* |
| `TASK_CREATE` (3) | `traceTASK_CREATE` | task id | priority | `T` | `[core/id]Name` | `preempt` | `create pri:N` |
| `TASK_DELETE` (4) | `traceTASK_DELETE` | task id | 0 | `STI` | `task` | `trigger` | `delete Name[id]` |
| `TASK_SUSPEND` (5) | `traceTASK_SUSPEND` | task id | 0 | `STI` | `task` | `trigger` | `suspend Name[id]` |
| `TASK_RESUME` (6) | `traceTASK_RESUME` | task id | 0 | `STI` | `task` | `trigger` | `resume Name[id]` |
| `TASK_RESUME_FROM_ISR` (7) | `traceTASK_RESUME_FROM_ISR` | task id | 0 | `STI` | `task` | `trigger` | `resume/isr` |
| `QUEUE_CREATE` (8) | `traceQUEUE_CREATE` | queue type† | object pointer | `STI` | `queue` / `mutex` / `sem`† | `trigger` | `create 0x........` |
| `QUEUE_SEND` (9) | `traceQUEUE_SEND` | queue type† | object pointer | `STI` | `queue` / `mutex` / `sem`† | `trigger` | `send` / `give`† `0x........` |
| `QUEUE_RECEIVE` (10) | `traceQUEUE_RECEIVE` | queue type† | object pointer | `STI` | `queue` / `mutex` / `sem`† | `trigger` | `recv` / `take`† `0x........` |
| `QUEUE_DELETE` (11) | `traceQUEUE_DELETE` | queue type† | object pointer | `STI` | `queue` / `mutex` / `sem`† | `trigger` | `delete 0x........` |
| `TASK_INCREMENT_TICK` (12) | `traceTASK_INCREMENT_TICK` | tick count | 0 | `STI` | `TICK` | `trigger` | `N` |
| `INTERVAL_START` (13) | `traceINTERVAL_START` | interval id | caller task id | `STI` | `interval_start` | `trigger` | `{id} tid:{task_id}` |
| `INTERVAL_STOP` (14) | `traceINTERVAL_STOP` | interval id | caller task id | `STI` | `interval_stop` | `trigger` | `{id} tid:{task_id}` |
| `TASK_PRIORITY_SET` (15) | `traceTASK_PRIORITY_SET` | task id | new priority | `STI` | `task` | `trigger` | `set_priority Name[id] pri:N` |
| `TASK_PRIORITY_INHERIT` (16) | `traceTASK_PRIORITY_INHERIT` | task id (mutex holder) | inherited priority | `STI` | `task` | `trigger` | `priority_inherit Name[id] pri:N` |
| `TASK_PRIORITY_DISINHERIT` (17) | `traceTASK_PRIORITY_DISINHERIT` | task id (mutex holder) | base priority | `STI` | `task` | `trigger` | `priority_disinherit Name[id] pri:N` |
| `TASK_SET_AFFINITY` (18) | `traceENTER_vTaskCoreAffinitySet` | task id | core affinity bitmask | `STI` | `task` | `trigger` | `affinity_set Name[id] 0xMASK` |
| `TAG` … `TAG7` (90–97) | `traceTAG(t, v)` | tag value | 0 | `STI` | `tag0_event` … `tag7_event` | `trigger` | `N` |

† **Queue type** (`param1`): `0` = queue, `1` = mutex, `2` = counting semaphore, `3` = binary semaphore, `4` = recursive mutex (`QUEUE_TYPE_*` in `btf_trace.h`). Mutex/semaphore rows use target `mutex` or `sem`; send/receive use `give`/`take` for mutex/sem and `send`/`recv` for queues.

`TASK_CREATE` also registers the task name in the trace task table (via `btf_trace_add_task()`). Task ids in BTF rows match `uxTCBNumber` from the kernel; interval `param2` uses the same id (`vTaskSetTaskNumber` keeps `uxTaskGetTaskNumber()` in sync at task creation).

---

### Memory & configuration

Default trace buffer size is controlled by `configMAX_TRACE_EVENTS` and `configMAX_TRACE_TASKS` in `FreeRTOSConfig.h` (and `MAX_TRACE_EVENTS` in the demo Makefile). Each `EVENT` is **16 bytes**; task names add `max_tasks × max_taskname_len` bytes. Total `trace.bin` size is `44 + max_tasks × max_taskname_len + max_events × 16` — see [`trace.bin` binary format](#tracebin-binary-format). When the event ring fills, newer events overwrite the oldest (ring wrap); `event_count` caps at `max_events`.

---

## Known limitations

| Area | Notes |
|------|-------|
| **SMP core limit** | `configNUMBER_OF_CORES` / `CORES` must be **1…31**. FreeRTOS V11.3.0 uses `(1U << configNUMBER_OF_CORES)` for affinity masks; that shift is undefined for N ≥ 32 |
| **Ring overflow** | When the event buffer fills, newer events overwrite the oldest; `#ringOverflow true` is written at BTF export |
| **Task table overflow** | When `task_id` is out of range, the event is still recorded but no name slot is written; `#taskTableOverflow true` is written at BTF export |
| **Truncation** | A crash or power loss before `btf_traceEND()` leaves `#truncated true` on live dump; `gentrace` also sets it for partial `trace.bin` files |
| **Parser parity** | BTF is parsed independently in Python (`btf_viewer.py`) and JavaScript (`btfParser.js`); golden parser tests live under `BTFViewer/tests/` |
| **CI / unit tests** | Run `make test-all` (desktop + web parser/stats tests); validate firmware traces with `make run` and viewer smoke tests |
| **Web viewer** | Trace files stay client-side; session state is stored in browser `localStorage` keyed by filename. Settings defaults match the desktop viewer (`btf-viewer-settings-v1`); font sizes use px on Web vs pt on Desktop with the same numeric defaults |

---

## License

MIT License
