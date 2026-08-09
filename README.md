# FreeRTOS-BTF-Trace

Record FreeRTOS scheduling in RAM, export it to standard trace formats, and analyse it offline — without a commercial tracer.

| Format | Use |
|--------|-----|
| **[BTF](https://assets.vector.com/cms/content/products/TA_Tool_Suite/Docs/BTF_Specification.pdf)** (Best Trace Format) | Timing and scheduling analysis in BTF Viewer or Eclipse Trace Compass |
| **VCD** (Value Change Dump) | Waveform viewers such as [GTKWave](http://gtkwave.sourceforge.net) |

![BTF Viewer](images/btfviewer.png)

[Live demo](https://apps.kuoping.com/btf_viewer.html?demo)

## Overview

Instrument FreeRTOS with trace hooks, capture context switches and sync events in a compact ring buffer, then convert the dump to BTF or VCD.

```
FreeRTOS hooks → ring buffer in RAM → trace.bin → gentrace → .btf / .vcd
                                                      ↓
                         BTF Viewer  ·  Trace Compass  ·  GTKWave
```

A related BareCTF + Trace Compass approach: [freertos-barectf](https://github.com/gpollo/freertos-barectf).

```
FreeRTOS-Trace/   Trace library (hooks, ring buffer, dump)
tools/            gentrace — binary dump → BTF or VCD
sim/              RV64 SMP simulator (`--cores N`)
Demo/             FreeRTOS SMP demo (RV64, runs under sim/)
BTFViewer/        Desktop (PySide6) and web (Vue) viewer
tracedata/        Sample `.btf.gz` / `.vcd` traces
```

Viewer user guide: [`BTFViewer/README.md`](BTFViewer/README.md) · diagnosis playbooks: [`BTFViewer/WORKFLOWS.md`](BTFViewer/WORKFLOWS.md) · porting: [`PORTING.md`](PORTING.md) · binary format: [`TRACE_FORMAT.md`](TRACE_FORMAT.md).

## Quick start

The bundled demo is **RISC-V RV64** and runs on `sim/`. Install [xPack RISC-V GCC](https://github.com/xpack-dev-tools/riscv-none-elf-gcc-xpack). The build looks for:

```
/opt/xpack-riscv-none-elf-gcc-15.2.0-1/bin/riscv-none-elf-gcc
```

Override with `RISCV_PREFIX` if needed (`make run RISCV_PREFIX=/path/to/riscv-none-elf-`).

```bash
make run            # single core
make CORES=2 run    # SMP
make CORES=8 run
```

The first run clones **FreeRTOS-Kernel V11.3.0**. After the simulator exits, `gentrace` writes `tracedata/trace.btf` and `tracedata/trace.vcd`.

```bash
pip install -r BTFViewer/requirements.txt
python BTFViewer/builds/btf_viewer.py tracedata/trace.btf
```

Sample traces: `tracedata/example.btf.gz`, `example-2cores.btf.gz`, `example-4cores.btf.gz`, `example-8cores.btf.gz`, `example-16cores.btf.gz`. Desktop and web open `.btf`, `.gz`, `.bz2`, and `.zip` the same way.

## Demo

`Demo/examples/freertos_test/` runs **11** tests. Tests 1–10 stay busy (yields only); test 11 uses `vTaskDelay` so tickless vs tickful idle is visible (`make TICKLESS=1 run`).

| # | Test | Exercises |
|---|------|-----------|
| 1 | Context-switch stress | Rapid voluntary yields across cores |
| 2 | Mutex contention | Priority-inheritance mutex under load |
| 3 | Counting semaphore + mutex | Mixed sync primitives |
| 4 | Task notifications | Direct-to-task notification API |
| 5 | Event groups | Multi-bit event sync |
| 6 | Queue stress | Producer / consumer queues |
| 7 | Task priority set | `vTaskPrioritySet` / `traceTASK_PRIORITY_SET` |
| 8 | Priority inversion | L / M / H on one core, 3 rounds (`T8_ROUNDS`) |
| 9 | Task suspend / resume | Suspend-while-blocked and while-running (`T9_SUBJECTS` × `T9_ROUNDS`) |
| 10 | Core affinity | Pin and migrate with `vTaskCoreAffinitySet` (no-op on 1 core) |
| 11 | Tickless idle | `vTaskDelay` windows for Trace Health (TICK vs TICKLESS) |

Interval `id` **0** wraps each test from the runner; **1–11** mark the matching test (inner loop for 1–6, whole test for 7–11).

## Viewing traces

**BTF Viewer** (desktop and browser) — task/core timelines, cursors, statistics, Analysis Findings, migration inspector, Trace Compare, AI Assistant, and PNG/SVG/Perfetto/CSV/HTML export.

```bash
python BTFViewer/builds/btf_viewer.py tracedata/example-8cores.btf.gz
# or open BTFViewer/builds/btf_viewer.html
```

Requirements: Python 3.8+ and PySide6 ≥ 6.4.

**Trace Compass** — open `tracedata/trace.btf` directly.

![Trace Compass](images/trace-compass.png)

**GTKWave** — `gtkwave tracedata/trace.vcd`

![VCD](images/vcd.png)

The demo also records **heap bytes in use** on every tick (`btf_traceTAG(0, …)` → STI `tag0_event`) and wraps tests with interval start/stop. Expand the tag row for a waveform; open **Statistics → Interval Analysis** for durations.

![Heap usage tag](images/memusage.png)

On SMP traces, **Core Migrations** plus the Heatmap / Chord inspector show where tasks bounce between cores.

![Migration inspector](images/migration.svg)

## Porting

Bring the library onto another FreeRTOS target: header, cycle counter, dump mode, start/stop, tags, and SMP locks — [`PORTING.md`](PORTING.md). Binary layout: [`TRACE_FORMAT.md`](TRACE_FORMAT.md).

## License

MIT
