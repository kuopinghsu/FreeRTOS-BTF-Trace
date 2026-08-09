# Porting guide

Integrate the trace library into your own FreeRTOS project. Demo build and viewing: [`README.md`](README.md). On-disk layout and event → BTF mapping: [`TRACE_FORMAT.md`](TRACE_FORMAT.md).

## 1. Include the header

In `FreeRTOSConfig.h`:

```c
#include "FreeRTOS-Trace/FreeRTOS-Trace.h"

#define configUSE_TRACE_FACILITY  1
#define configMAX_TRACE_EVENTS    4096   /* ring capacity; 16 bytes each */
#define configMAX_TRACE_TASKS     64
```

Optional knobs (defaults in `FreeRTOS-Trace.h` / `btf_trace.h`):

| Macro | Default | Role |
|-------|---------|------|
| `configMAX_TRACE_TASK_NAME_LEN` | 8 | Bytes stored per task name (plus NUL; slot is 4-byte aligned) |
| `configINCLUDE_SCHEDULING` | 1 | Switch, create/delete, suspend/resume, priority, affinity |
| `configINCLUDE_TAGS` | 1 | `traceTAG` / interval start–stop |
| `configINCLUDE_QUEUE_EVENTS` | 1 | Queue / mutex / semaphore STI |
| `configINCLUDE_OSTICK_EVENTS` | 1 | TICK STI |

Add `FreeRTOS-Trace/` to the include path and compile `FreeRTOS-Trace/btf_trace.c`.

## 2. Time source

In `FreeRTOS-Trace/btf_port.h`, define `xGetCycles()` as a free-running **`uint32_t`** counter (DWT CYCCNT, GPT, `mtime`, …). Wrap at 2³² is expected; `gentrace` / `btf_dump()` extend timestamps offline using `core_clock` (`configCPU_CLOCK_HZ`).

The RISC-V demo maps `xGetCycles()` to the lower 32 bits of CLINT `mtime` via `portGET_RUN_TIME_COUNTER_VALUE()`. Non-RISC-V builds hit `#error` until you implement the hook.

## 3. Dump mode

Set these in `btf_port.h` (or before including the header):

| Mode | How |
|------|-----|
| File dump (default on RISC-V) | `HAVE_FILE_DUMP` — `traceEND()` writes `TRACE_DUMP_FILENAME` (default `trace.bin`) via `fopen` / `fwrite` / `fclose` |
| Live stdout BTF | `#define PRINT_BTF_DUMP` — `btf_dump()` prints BTF 2.2.0 CSV at `traceEND()`. `TIMESCALE_US` 1 → `#timeScale us`, 0 → `ns` |
| Buffer only | Define neither — keep events in RAM and read the `trace_data` symbol over JTAG after the run |

File dump needs a working C library `FILE` API. On bare metal without stdio, use buffer-only or live dump.

## 4. Start and stop

Call `traceSTART()` before the scheduler and `traceEND()` when the run finishes (typically from the last task).

```c
int main( void )
{
#if configUSE_TRACE_FACILITY
    traceSTART();
#endif
    xTaskCreate( ... );
    vTaskStartScheduler();
}

/* Inside the task that finishes last: */
#if configUSE_TRACE_FACILITY
    traceEND();
#endif
```

Size the ring for the longest capture you care about. When it fills, new events overwrite the oldest and export sets `#ringOverflow true`.

## 5. Tags and intervals

With `configINCLUDE_TAGS` (default **1**):

```c
traceTAG( 0, (int) allocated );     /* STI tag0_event … tag7_event */

traceINTERVAL_START( 1 );
do_work();
traceINTERVAL_STOP( 1 );            /* note: "{id} tid:{task_id}" */
```

| Macro | Purpose |
|-------|---------|
| `traceTAG( t, v )` | Periodic sample; `t` = 0…7, `v` = 32-bit payload |
| `traceINTERVAL_START( id )` | Start a timed region (`param1` = `id`, `param2` = caller task id) |
| `traceINTERVAL_STOP( id )` | End the same region |

Prefer these macros in task code (they take the trace lock). Use `btf_traceTAG` / `btf_traceINTERVAL_*` only when you already hold the lock or the wrappers are unsuitable.

The demo records heap bytes in use from `vApplicationTickHook()` as `traceTAG(0, …)`. Interval **0** wraps each stress test; **1–11** mark the matching test — see [`README.md`](README.md#demo).

## 6. SMP

Hooks use `taskENTER_CRITICAL` (task context) or `taskENTER_CRITICAL_FROM_ISR` (ISR / context-switch). The RISC-V SMP port (`Demo/port/RISC-V/port.c`) implements both locks as **recursive** spinlocks so `traceTASK_SWITCHED_OUT` / `IN` can run inside `vTaskSwitchContext` while the ISR lock is already held. Non-recursive locks will deadlock — match that pattern on other SMP ports.

**Core affinity STI** (`affinity_set Name[id] 0xMASK` on the `task` channel):

- `configUSE_CORE_AFFINITY` = `1`
- `configINCLUDE_SCHEDULING` = `1`
- FreeRTOS V11 fires `traceENTER_vTaskCoreAffinitySet` (there is no `traceTASK_CORE_AFFINITY_SET` macro); the library records the bitmask

BTF Viewer compares observed cores against the mask and flags violations. `configNUMBER_OF_CORES` must be **1–31**.

## 7. Convert and open

```bash
tools/gentrace trace.bin trace.btf
tools/gentrace -v trace.bin trace.vcd
```

Open `.btf` in BTF Viewer or Trace Compass; open `.vcd` in GTKWave. Field mapping and quality flags (`#ringOverflow`, `#taskTableOverflow`, `#truncated`): [`TRACE_FORMAT.md`](TRACE_FORMAT.md).
