# FreeRTOS-BTF-Trace Porting Guide

This guide explains how to integrate the trace library with an existing FreeRTOS target.

| Document | Purpose |
|---|---|
| [README.md](README.md) | Build the demo, capture events, and open a trace |
| [TRACE_FORMAT.md](TRACE_FORMAT.md) | Understand the binary layout and BTF event mapping |
| [BTFViewer/WORKFLOWS.md](BTFViewer/WORKFLOWS.md) | Follow trace-analysis procedures |

## Porting checklist

- [ ] Enable the FreeRTOS trace facility.
- [ ] Include `FreeRTOS-Trace.h`.
- [ ] Compile `btf_trace.c`.
- [ ] Implement `xGetCycles()`.
- [ ] Set `configCPU_CLOCK_HZ` to the counter frequency.
- [ ] Select file, live, or buffer-only output.
- [ ] Call `traceSTART()` before starting the scheduler.
- [ ] Call `traceEND()` when capture ends.
- [ ] Size the task table and event ring.
- [ ] Verify trace locking on SMP targets.
- [ ] Convert `trace.bin` and check the quality flags.

## 1. Add the trace library

Add these definitions to `FreeRTOSConfig.h`:

```c
#include "FreeRTOS-Trace/FreeRTOS-Trace.h"

#define configUSE_TRACE_FACILITY  1
#define configMAX_TRACE_EVENTS    4096   /* Ring capacity; 16 bytes per event. */
#define configMAX_TRACE_TASKS     64
```

Add `FreeRTOS-Trace/` to the compiler include path and compile:

```text
FreeRTOS-Trace/btf_trace.c
```

### Configuration options

| Macro | Default | Purpose |
|---|---:|---|
| `configMAX_TRACE_TASK_NAME_LEN` | 8 | Maximum stored task-name length; the NUL-terminated slot is aligned to 4 bytes |
| `configINCLUDE_SCHEDULING` | 1 | Record task switching, lifecycle, priority, and affinity events |
| `configINCLUDE_TAGS` | 1 | Record tags and interval start/stop events |
| `configINCLUDE_QUEUE_EVENTS` | 1 | Record queue, mutex, and semaphore STI events |
| `configINCLUDE_OSTICK_EVENTS` | 1 | Record TICK STI events |

Default values are defined in `FreeRTOS-Trace.h` and `btf_trace.h`.

## 2. Provide the time source

Implement this function in `FreeRTOS-Trace/btf_port.h`:

```c
uint32_t xGetCycles(void);
```

The function must return a free-running 32-bit counter. Suitable sources include DWT CYCCNT, GPT, `mtime`, or an equivalent hardware counter.

Requirements:

- A 2³² counter wrap is expected.
- `configCPU_CLOCK_HZ` and the exported `core_clock` must match the counter frequency.
- The counter must remain consistent across all captured events.

`gentrace` and `btf_dump()` reconstruct wrapped timestamps during export.

### RISC-V demo

The RISC-V demo maps `xGetCycles()` to the lower 32 bits of CLINT `mtime` through:

```c
portGET_RUN_TIME_COUNTER_VALUE()
```

Other targets stop at `#error` until this port hook is implemented.

## 3. Select an output mode

Configure the mode in `btf_port.h`, or define it before including the trace header.

| Mode | Configuration | Result |
|---|---|---|
| **File dump** | `HAVE_FILE_DUMP` | `traceEND()` writes `TRACE_DUMP_FILENAME`; the default is `trace.bin` |
| **Live BTF** | `PRINT_BTF_DUMP` | `btf_dump()` prints BTF 2.2.0 CSV when `traceEND()` runs |
| **Buffer only** | Define neither option | Trace data remains in RAM and can be read from `trace_data` with a debugger |

Live BTF supports these time scales:

| `TIMESCALE_US` | BTF header |
|---:|---|
| 1 | `#timeScale us` |
| 0 | `#timeScale ns` |

File output requires a working C library `FILE` implementation. On a bare-metal target without standard I/O, use live BTF or buffer-only mode.

## 4. Start and stop capture

Call `traceSTART()` before starting the scheduler:

```c
int main(void)
{
#if configUSE_TRACE_FACILITY
    traceSTART();
#endif

    xTaskCreate(...);
    vTaskStartScheduler();
}
```

Call `traceEND()` when the capture period finishes:

```c
#if configUSE_TRACE_FACILITY
    traceEND();
#endif
```

### Event-ring size

`configMAX_TRACE_EVENTS` sets the number of retained 16-byte event records.

When the ring is full:

1. A new event overwrites the oldest event.
2. `event_count` remains equal to `max_events`.
3. The BTF export contains `#ringOverflow true`.

Choose a capacity large enough for the workload period that you need to analyze.

## 5. Add application instrumentation

Enable instrumentation with `configINCLUDE_TAGS=1`.

### Tags

Use a tag to record a 32-bit application value:

```c
traceTAG(0, (int)allocated);
```

| Item | Meaning |
|---|---|
| `traceTAG(t, v)` | Record value `v` on tag channel `t`, where `t` is 0–7 |
| BTF target | `tag0_event` through `tag7_event` |

### Intervals

Use an interval to mark the start and end of an application phase:

```c
traceINTERVAL_START(1);
do_work();
traceINTERVAL_STOP(1);
```

| API | Stored data |
|---|---|
| `traceINTERVAL_START(id)` | `param1=id`, `param2=caller task id` |
| `traceINTERVAL_STOP(id)` | The same interval and task IDs |
| BTF note | `{id} tid:{task_id}` |

Use `traceTAG()` and `traceINTERVAL_*()` in normal task code because these wrappers acquire the trace lock.

Use `btf_traceTAG()` or `btf_traceINTERVAL_*()` only when the caller already holds the required lock or cannot use the wrappers.

The demo uses tag 0 for heap bytes and interval IDs 0–11 for its test regions.

## 6. Meet the SMP requirements

Trace hooks run from two contexts:

| Context | Lock operation |
|---|---|
| Task context | `taskENTER_CRITICAL` |
| ISR or context-switch path | `taskENTER_CRITICAL_FROM_ISR` |

The RISC-V SMP port uses recursive spinlocks for both paths. This allows `traceTASK_SWITCHED_OUT` and `traceTASK_SWITCHED_IN` to run inside `vTaskSwitchContext` while the ISR lock is held.

> A non-recursive lock can deadlock in this path. An SMP port must provide equivalent recursive behavior.

### Core-affinity tracing

Enable both options:

```c
#define configUSE_CORE_AFFINITY   1
#define configINCLUDE_SCHEDULING  1
```

FreeRTOS V11 calls `traceENTER_vTaskCoreAffinitySet`. The trace library converts the hook to an affinity event:

```text
affinity_set Name id 0xMASK
```

BTFViewer compares the cores used by the task with this affinity mask.

`configNUMBER_OF_CORES` must be from **1 through 31**.

## 7. Convert the capture

For file-output mode, convert `trace.bin` after capture:

```bash
tools/gentrace trace.bin trace.btf
tools/gentrace -v trace.bin trace.vcd
```

| Output | Viewer |
|---|---|
| `.btf` | BTFViewer or Eclipse Trace Compass |
| `.vcd` | GTKWave |

## 8. Validate the port

Validate the capture before using it for performance analysis.

| Check | Expected result |
|---|---|
| Open the BTF file | The viewer accepts the header and event layout |
| Check task names | Expected names appear; the task table is large enough |
| Check the timeline | Timestamps are monotonic after wrap reconstruction |
| Check core IDs | All IDs are valid for the configured SMP system |
| Check TICK events | Events appear when `configINCLUDE_OSTICK_EVENTS=1` |
| Check tags and intervals | Values and start/stop pairs are correct |
| Check affinity events | Events appear when affinity and scheduling hooks are enabled |
| Check quality metadata | No unexpected capture-quality flags appear |

### Quality flags

| Flag | Meaning |
|---|---|
| `#ringOverflow true` | The ring wrapped and the oldest events were lost |
| `#taskTableOverflow true` | A task ID had no available task-name slot |
| `#truncated true` | `traceEND()` was not called, or the binary dump is incomplete |

See [TRACE_FORMAT.md](TRACE_FORMAT.md) for the exact binary layout and BTF mapping.
