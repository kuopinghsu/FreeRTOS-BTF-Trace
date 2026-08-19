# FreeRTOS-BTF-Trace

FreeRTOS-BTF-Trace records scheduling and synchronization events in a compact RAM ring buffer. The included tools convert the captured data to:

- **BTF** (Best Trace Format) for BTFViewer and Eclipse Trace Compass.
- **VCD** (Value Change Dump) for GTKWave.

![BTF trace overview](images/btftrace.png)

## Documentation

| Document | Purpose |
|---|---|
| **README.md** | Build the demo, capture events, and open a trace |
| **[PORTING.md](PORTING.md)** | Integrate the trace library with another FreeRTOS target |
| **[TRACE_FORMAT.md](TRACE_FORMAT.md)** | Understand the `trace.bin` layout and BTF event mapping |
| **[BTFViewer/README.md](BTFViewer/README.md)** | Install and use BTFViewer |
| **[BTFViewer/WORKFLOWS.md](BTFViewer/WORKFLOWS.md)** | Follow RTOS analysis procedures |
| **[BTFViewer/AI.md](BTFViewer/AI.md)** | Configure and use the BTFViewer AI Assistant |

## How it works

1. FreeRTOS trace hooks record events in a RAM ring buffer.
2. The application exports the buffer as `trace.bin`.
3. `gentrace` converts `trace.bin` to BTF and VCD.
4. Open the converted trace in the appropriate viewer.

| Output | Use |
|---|---|
| `.btf` | Scheduling, timing, synchronization, and SMP analysis in BTFViewer or Trace Compass |
| `.vcd` | Signal-style waveform inspection in GTKWave |

![BTFViewer](images/btfviewer.png)

[Open the BTFViewer live demo](https://apps.kuoping.com/btf_viewer.html?demo)

## Repository layout

| Path | Contents |
|---|---|
| `FreeRTOS-Trace/` | FreeRTOS hooks, ring buffer, and trace dump support |
| `tools/` | `gentrace` converter for BTF and VCD output |
| `sim/` | RISC-V RV64 SMP simulator |
| `Demo/` | FreeRTOS SMP demo workloads |
| `BTFViewer/` | Desktop and Web trace-analysis applications |
| `tracedata/` | Sample BTF and VCD traces |

## Quick start

The bundled demo runs on the RISC-V RV64 simulator in `sim/`.

### 1. Install the toolchain

Install xPack RISC-V GCC. The default compiler path is:

```text
/opt/xpack-riscv-none-elf-gcc-15.2.0-1/bin/riscv-none-elf-gcc
```

To use another installation, set `RISCV_PREFIX`:

```bash
make run RISCV_PREFIX=/path/to/riscv-none-elf-
```

### 2. Build and capture

```bash
make run            # single core
make CORES=2 run    # 2-core SMP
make CORES=8 run    # 8-core SMP
```

On the first run, the build clones **FreeRTOS-Kernel V11.3.0**. When the simulator exits, `gentrace` creates:

```text
tracedata/trace.btf
tracedata/trace.vcd
```

### 3. Open the BTF trace

Install the Desktop application requirements and open the trace:

```bash
pip install -r BTFViewer/requirements.txt
python BTFViewer/builds/btf_viewer.py tracedata/trace.btf
```

BTFViewer Desktop and Web support `.btf`, `.gz`, `.bz2`, and `.zip` files.

Sample captures are available in `tracedata/`:

```text
example.btf.gz
example-2cores.btf.gz
example-4cores.btf.gz
example-8cores.btf.gz
example-16cores.btf.gz
```

## Demo workload

`Demo/examples/freertos_test/` contains 11 tests. Tests 1–10 use yields to keep the workload active. Test 11 uses `vTaskDelay` to compare normal ticks with tickless idle.

Enable tickless idle with:

```bash
make TICKLESS=1 run
```

| # | Test | Purpose |
|---:|---|---|
| 1 | Context-switch stress | Generate rapid voluntary yields across cores |
| 2 | Mutex contention | Exercise a priority-inheritance mutex under load |
| 3 | Counting semaphore and mutex | Combine synchronization primitives |
| 4 | Task notifications | Exercise direct-to-task notifications |
| 5 | Event groups | Exercise multi-bit event synchronization |
| 6 | Queue stress | Run producer and consumer queues |
| 7 | Task priority change | Exercise `vTaskPrioritySet` and `traceTASK_PRIORITY_SET` |
| 8 | Priority inversion | Run low-, medium-, and high-priority tasks on one core for `T8_ROUNDS` |
| 9 | Task suspend and resume | Suspend blocked or running tasks for `T9_SUBJECTS × T9_ROUNDS` |
| 10 | Core affinity | Pin and migrate tasks with `vTaskCoreAffinitySet` |
| 11 | Tickless idle | Compare TICK and TICKLESS behavior during `vTaskDelay` windows |

Interval ID **0** covers each complete test. IDs **1–11** identify individual tests.

## Trace viewers

### BTFViewer

BTFViewer provides task and core timelines, measurement cursors, Statistics, Analysis Findings, migration inspection, trace comparison, AI-assisted investigation, and export.

```bash
python BTFViewer/builds/btf_viewer.py tracedata/example-8cores.btf.gz
```

For the Web application, open `BTFViewer/builds/btf_viewer.html` in a browser.

Desktop requirements: Python 3.8+ and PySide6 6.4 or later.

See **[BTFViewer/WORKFLOWS.md](BTFViewer/WORKFLOWS.md)** for analysis procedures.

### Eclipse Trace Compass

Open `tracedata/trace.btf` directly.

![Trace Compass](images/trace-compass.png)

### GTKWave

```bash
gtkwave tracedata/trace.vcd
```

![GTKWave VCD view](images/vcd.png)

## Custom instrumentation

The demo records heap usage on every tick:

```c
btf_traceTAG(0, ...);
```

The value appears in BTF as the STI channel `tag0_event`. Interval start and stop events mark individual test regions.

![Heap usage tag](images/memusage.png)

SMP traces also support task-migration and migration-corridor analysis.

![Migration inspector](images/migration.svg)

## Porting

A port requires:

- FreeRTOS trace-hook integration.
- A free-running 32-bit cycle counter.
- One supported trace-dump mode.

Call `traceSTART()` to begin capture and `traceEND()` to stop it.

See **[PORTING.md](PORTING.md)** for configuration, time-source requirements, dump modes, tags, intervals, and SMP locking.

See **[TRACE_FORMAT.md](TRACE_FORMAT.md)** for the binary layout, event encoding, BTF mapping, and trace-quality flags.

## Related project

[freertos-barectf](https://github.com/gpollo/freertos-barectf) provides a related BareCTF and Trace Compass implementation.

## License

MIT
