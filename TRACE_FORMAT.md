# Trace format

On-disk `trace.bin` layout, BTF export mapping, and quality metadata. Build and viewing: [`README.md`](README.md). Integrating on a new target: [`PORTING.md`](PORTING.md). Structs and `event_t`: `FreeRTOS-Trace/btf_trace.h`.

## `trace.bin`

`traceEND()` writes a little-endian blob: a 44-byte header, the task-name table, then a ring of 16-byte events.

```
┌─────────────────────────────────────────────────────────────┐
│ TRACE_HEADER  (44 bytes)                                    │
├─────────────────────────────────────────────────────────────┤
│ task_lists[max_tasks × max_taskname_len]                    │
│   NUL-terminated name per task id (uxTCBNumber)             │
├─────────────────────────────────────────────────────────────┤
│ event_lists[max_events]  (16-byte EVENT records)            │
└─────────────────────────────────────────────────────────────┘
```

Size (bytes):

```
44 + max_tasks × max_taskname_len + max_events × 16
```

`max_tasks`, `max_taskname_len`, and `max_events` come from the header (set at `traceSTART()` from `configMAX_TRACE_TASKS`, `ALIGN4(configMAX_TRACE_TASK_NAME_LEN+1)`, and `configMAX_TRACE_EVENTS`).

### Header (44 bytes, little-endian)

| Offset | Field | Type | Description |
|-------:|-------|------|-------------|
| 0 | `header` | `char[4]` | Magic `B` `T` `F` `2` |
| 4 | `tag` | `uint32_t` | Endian marker — must be `1` |
| 8 | `version` | `uint32_t` | `TRACE_VERSION` = `(major<<16)\|minor` (1.4 → `0x00010004`) |
| 12 | `core_clock` | `uint32_t` | CPU frequency (Hz) |
| 16 | `num_cores` | `uint32_t` | `configNUMBER_OF_CORES` |
| 20 | `max_tasks` | `uint32_t` | Task name table slots |
| 24 | `max_taskname_len` | `uint32_t` | Bytes per name slot (4-byte aligned) |
| 28 | `max_events` | `uint32_t` | Ring buffer capacity |
| 32 | `task_count` | `uint32_t` | `TASK_CREATE` events recorded |
| 36 | `event_count` | `uint32_t` | Events in buffer (≤ `max_events`) |
| 40 | `current_index` | `uint32_t` | Next write index; oldest event when full |

### Task name table

- Slot `task_id` is the FreeRTOS **task id** (`uxTCBNumber`), not a dense 0…N−1 index.
- Written on `traceTASK_CREATE`. If `task_id` is `0` or ≥ `configMAX_TRACE_TASKS`, the name is omitted but the event is still recorded (`#taskTableOverflow true` at export).

### Event record (16 bytes)

| Offset | Field | Type | Description |
|-------:|-------|------|-------------|
| 0 | `timestamp` | `uint32_t` | Cycle counter from `xGetCycles()` (wraps at 2³²; extended offline) |
| 4 | `param1` | `uint32_t` | Event-specific |
| 8 | `param2` | `uint32_t` | Event-specific |
| 12 | `types` | `uint32_t` | `event_t` + optional core id |

**`types` bits**

| Bits | Meaning |
|------|---------|
| `[23:0]` | `event_t` (see `btf_trace.h`) |
| `[30:24]` | Core id when `num_cores` > 1 (`portGET_CORE_ID()`) |
| `[31]` | Unused |

On single-core builds, `types` is just the `event_t` value.

### Ring buffer

Events append at `current_index` (mod `max_events`). When `event_count == max_events`, replay starts at `current_index` (oldest) through `current_index − 1`. Otherwise replay starts at `0`. After wrap, new events overwrite the oldest; `event_count` stays at `max_events`.

### Timestamps

`timestamp` is a free-running 32-bit counter (`xGetCycles()` in `btf_port.h`). `gentrace` and `btf_dump()` detect wrap and build monotonic 64-bit times scaled by `core_clock`.

## BTF quality metadata

After `#version`, `#creator`, `#creationDate`, and `#timeScale`, export may add:

| Meta | Meaning |
|------|---------|
| `#ringOverflow true` | Ring wrapped; oldest events lost |
| `#taskTableOverflow true` | Task id missing from the name table |
| `#truncated true` | `traceEND()` not called, or `trace.bin` shorter than a full blob |

A clean trace omits these lines. They are inferred at export, not stored in the binary header. BTF Viewer shows a banner when any flag is set.

## Binary → BTF dump mapping

`tools/gentrace` and live `btf_dump()` (`PRINT_BTF_DUMP` in `btf_port.h`) turn each `EVENT` into one BTF 2.2.0 CSV line. `param1` / `param2` are the 32-bit fields in the binary record. On SMP, core id is taken from `types[30:24]` and appears as `Core_N` (or `[N/id]Name` on switch-in).

### File header

```
#version 2.2.0
#creator FreeRTOS trace logger
#creationDate YYYY-MM-DDTHH:MM:SSZ
#timeScale us
```

Optional quality lines may follow (`#ringOverflow`, `#taskTableOverflow`, `#truncated`). Then one synthetic clock line per core (not stored in the event ring):

```
<t>,Core_0,0,C,Core_0,0,set_frequency,<core_clock>
```

### Event line

```
time, source, 0, type, target, 0, action, note
```

Example:

```
214276,Core_0,0,STI,interval_start,0,trigger,0 tid:1
215514,Core_0,0,T,[0/0007]CS,0,resume,
217432,Core_1,0,STI,task,0,trigger,suspend SR0[271]
```

| Event (`event_t`) | Hook / API | `param1` | `param2` | Type | Target | Action | Note |
|-------------------|------------|----------|----------|------|--------|--------|------|
| `TASK_SWITCHED_IN` (1) | `traceTASK_SWITCHED_IN` | task id | 0 | `T` | `[core/id]Name` | `resume` | *(empty)* — `source` is the previous task on that core |
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
| `TASK_PRIORITY_INHERIT` (16) | `traceTASK_PRIORITY_INHERIT` | holder task id | inherited pri | `STI` | `task` | `trigger` | `priority_inherit Name[id] pri:N` |
| `TASK_PRIORITY_DISINHERIT` (17) | `traceTASK_PRIORITY_DISINHERIT` | holder task id | base pri | `STI` | `task` | `trigger` | `priority_disinherit Name[id] pri:N` |
| `TASK_SET_AFFINITY` (18) | `traceENTER_vTaskCoreAffinitySet` | task id | affinity mask | `STI` | `task` | `trigger` | `affinity_set Name[id] 0xMASK` |
| `TAG` … `TAG7` (90–97) | `traceTAG(t, v)` | tag value | 0 | `STI` | `tag0_event` … `tag7_event` | `trigger` | `N` |

† **Queue type** (`param1`, `QUEUE_TYPE_*` in `btf_trace.h`):

| `param1` | Kind | Target | Send / receive actions |
|---------:|------|--------|------------------------|
| 0 | Queue | `queue` | `send` / `recv` |
| 1 | Mutex | `mutex` | `give` / `take` |
| 2 | Counting semaphore | `sem` | `give` / `take` |
| 3 | Binary semaphore | `sem` | `give` / `take` |
| 4 | Recursive mutex | `mutex` | `give` / `take` |

`TASK_CREATE` also writes the name into the task table. Task ids in BTF rows match `uxTCBNumber`; interval `param2` uses the same id. Task labels are `[core/id]Name` with a zero-padded four-digit id (e.g. `[0/0007]CS`).

## Limits

| Area | Notes |
|------|-------|
| SMP cores | `configNUMBER_OF_CORES` is **1–31** (FreeRTOS affinity shift is undefined for N ≥ 32) |
| Ring overflow | Full buffer overwrites oldest events; `#ringOverflow true` on export |
| Task table | Out-of-range task ids are recorded without a name; `#taskTableOverflow true` |
| Truncation | Missing `traceEND()` or a short `trace.bin` → `#truncated true` |
