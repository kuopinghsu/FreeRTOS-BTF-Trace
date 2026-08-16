# FreeRTOS-BTF-Trace — Trace Format Reference

Reference for the on-disk `trace.bin` layout, event encoding, BTF mapping, and trace-quality metadata.

| Document | Contents |
|---|---|
| [README.md](README.md) | Build, demo, and viewing |
| [PORTING.md](PORTING.md) | Target integration |
| `FreeRTOS-Trace/btf_trace.h` | C structures and `event_t` definitions |

## 1. File layout

`traceEND()` writes one little-endian binary blob:

```text
┌─────────────────────────────────────────────────────────────┐
│ TRACE_HEADER — 44 bytes                                     │
├─────────────────────────────────────────────────────────────┤
│ task_lists[max_tasks × max_taskname_len]                    │
│   NUL-terminated task name per FreeRTOS task id             │
├─────────────────────────────────────────────────────────────┤
│ event_lists[max_events]                                     │
│   16-byte EVENT records                                     │
└─────────────────────────────────────────────────────────────┘
```

Total size:

```text
44 + max_tasks × max_taskname_len + max_events × 16
```

The size fields are set by `traceSTART()` from:

| Binary field | Configuration |
|---|---|
| `max_tasks` | `configMAX_TRACE_TASKS` |
| `max_taskname_len` | `ALIGN4(configMAX_TRACE_TASK_NAME_LEN + 1)` |
| `max_events` | `configMAX_TRACE_EVENTS` |

## 2. Binary header

The header is **44 bytes**, little-endian.

| Offset | Field | Type | Meaning |
|---:|---|---|---|
| 0 | `header` | `char[4]` | Magic `BTF2` |
| 4 | `tag` | `uint32_t` | Endian marker; must be `1` |
| 8 | `version` | `uint32_t` | `(major << 16) \| minor`; 1.4 = `0x00010004` |
| 12 | `core_clock` | `uint32_t` | Counter/CPU frequency in Hz |
| 16 | `num_cores` | `uint32_t` | `configNUMBER_OF_CORES` |
| 20 | `max_tasks` | `uint32_t` | Task-name table slots |
| 24 | `max_taskname_len` | `uint32_t` | Bytes per aligned task-name slot |
| 28 | `max_events` | `uint32_t` | Event-ring capacity |
| 32 | `task_count` | `uint32_t` | `TASK_CREATE` events recorded |
| 36 | `event_count` | `uint32_t` | Events currently retained |
| 40 | `current_index` | `uint32_t` | Next ring write index; oldest when full |

## 3. Task-name table

Each slot stores a NUL-terminated task name.

- The slot index is the FreeRTOS **task id** (`uxTCBNumber`).
- It is **not** a dense `0…N−1` index.
- Names are written by `traceTASK_CREATE`.
- If `task_id == 0` or `task_id >= configMAX_TRACE_TASKS`, the event is still recorded but the name is omitted.
- Export marks that condition with `#taskTableOverflow true`.

## 4. Event record

Every event occupies **16 bytes**.

| Offset | Field | Type | Meaning |
|---:|---|---|---|
| 0 | `timestamp` | `uint32_t` | Free-running cycle count |
| 4 | `param1` | `uint32_t` | Event-specific parameter |
| 8 | `param2` | `uint32_t` | Event-specific parameter |
| 12 | `types` | `uint32_t` | `event_t` plus optional core id |

### `types` encoding

| Bits | Meaning |
|---|---|
| `[23:0]` | `event_t` |
| `[30:24]` | Core id on SMP (`portGET_CORE_ID()`) |
| `[31]` | Unused |

On a single-core build, `types` is simply the `event_t` value.

## 5. Ring-buffer ordering

Events append at:

```text
current_index % max_events
```

```text
event_count < max_events
    → replay event 0 … event_count-1

event_count == max_events
    → current_index is the oldest event
    → replay current_index … end
    → then 0 … current_index-1
```

After the ring wraps, new events overwrite the oldest and `event_count` remains equal to `max_events`.

The export contains `#ringOverflow true` after a wrap.

## 6. Timestamp reconstruction

`timestamp` comes from the free-running 32-bit `xGetCycles()` counter.

```text
32-bit counter
     ↓
detect 2³² wrap
     ↓
extend to monotonic 64-bit time
     ↓
scale using core_clock
     ↓
BTF timestamp
```

Both `gentrace` and live `btf_dump()` perform this reconstruction.

## 7. BTF quality metadata

A BTF export starts with normal BTF metadata and may add trace-quality flags.

| Metadata | Meaning |
|---|---|
| `#ringOverflow true` | Event ring wrapped; oldest events were lost |
| `#taskTableOverflow true` | At least one task id had no task-name slot |
| `#truncated true` | `traceEND()` was not called, or `trace.bin` is shorter than a complete blob |

A clean trace omits these lines. The flags are inferred during export and are not stored in the 44-byte binary header. BTF Viewer shows a warning banner when any flag is present.

## 8. Binary → BTF conversion

`tools/gentrace` and live `btf_dump()` convert each binary `EVENT` to one BTF 2.2.0 CSV line.

### 8.1 BTF file header

```text
#version 2.2.0
#creator FreeRTOS trace logger
#creationDate YYYY-MM-DDTHH:MM:SSZ
#timeScale us
```

Quality metadata, when present, follows the header. A synthetic clock line is emitted for each core:

```text
<t>,Core_0,0,C,Core_0,0,set_frequency,<core_clock>
```

These clock lines are not stored in the event ring.

### 8.2 BTF event-line shape

```text
time, source, 0, type, target, 0, action, note
```

Examples:

```text
214276,Core_0,0,STI,interval_start,0,trigger,0 tid:1
215514,Core_0,0,T,[0/0007]CS,0,resume,
217432,Core_1,0,STI,task,0,trigger,suspend SR0[271]
```

On SMP, the core id comes from `types[30:24]` and is rendered as `Core_N`, or inside `[N/id]Name` for task switch events.

## 9. Event mapping

| Event (`event_t`) | Hook / API | `param1` | `param2` | BTF type | Target | Action | Note |
|---|---|---|---|---|---|---|---|
| `TASK_SWITCHED_IN` (1) | `traceTASK_SWITCHED_IN` | task id | 0 | `T` | `[core/id]Name` | `resume` | Empty; source is previous task |
| `TASK_SWITCHED_OUT` (2) | `traceTASK_SWITCHED_OUT` | task id | 0 | `T` | `[core/id]Name` | `preempt` | Empty |
| `TASK_CREATE` (3) | `traceTASK_CREATE` | task id | priority | `T` | `[core/id]Name` | `preempt` | `create pri:N` |
| `TASK_DELETE` (4) | `traceTASK_DELETE` | task id | 0 | `STI` | `task` | `trigger` | `delete Name[id]` |
| `TASK_SUSPEND` (5) | `traceTASK_SUSPEND` | task id | 0 | `STI` | `task` | `trigger` | `suspend Name[id]` |
| `TASK_RESUME` (6) | `traceTASK_RESUME` | task id | 0 | `STI` | `task` | `trigger` | `resume Name[id]` |
| `TASK_RESUME_FROM_ISR` (7) | `traceTASK_RESUME_FROM_ISR` | task id | 0 | `STI` | `task` | `trigger` | `resume/isr` |
| `QUEUE_CREATE` (8) | `traceQUEUE_CREATE` | queue type | object pointer | `STI` | queue/mutex/sem | `trigger` | `create 0x........` |
| `QUEUE_SEND` (9) | `traceQUEUE_SEND` | queue type | object pointer | `STI` | queue/mutex/sem | `trigger` | send/give + address |
| `QUEUE_RECEIVE` (10) | `traceQUEUE_RECEIVE` | queue type | object pointer | `STI` | queue/mutex/sem | `trigger` | recv/take + address |
| `QUEUE_DELETE` (11) | `traceQUEUE_DELETE` | queue type | object pointer | `STI` | queue/mutex/sem | `trigger` | `delete 0x........` |
| `TASK_INCREMENT_TICK` (12) | `traceTASK_INCREMENT_TICK` | tick count | 0 | `STI` | `TICK` | `trigger` | `N` |
| `INTERVAL_START` (13) | `traceINTERVAL_START` | interval id | caller task id | `STI` | `interval_start` | `trigger` | `{id} tid:{task_id}` |
| `INTERVAL_STOP` (14) | `traceINTERVAL_STOP` | interval id | caller task id | `STI` | `interval_stop` | `trigger` | `{id} tid:{task_id}` |
| `TASK_PRIORITY_SET` (15) | `traceTASK_PRIORITY_SET` | task id | new priority | `STI` | `task` | `trigger` | `set_priority Name[id] pri:N` |
| `TASK_PRIORITY_INHERIT` (16) | `traceTASK_PRIORITY_INHERIT` | holder id | inherited priority | `STI` | `task` | `trigger` | `priority_inherit Name[id] pri:N` |
| `TASK_PRIORITY_DISINHERIT` (17) | `traceTASK_PRIORITY_DISINHERIT` | holder id | base priority | `STI` | `task` | `trigger` | `priority_disinherit Name[id] pri:N` |
| `TASK_SET_AFFINITY` (18) | `traceENTER_vTaskCoreAffinitySet` | task id | affinity mask | `STI` | `task` | `trigger` | `affinity_set Name[id] 0xMASK` |
| `TAG … TAG7` (90–97) | `traceTAG(t, v)` | tag value | 0 | `STI` | `tag0_event … tag7_event` | `trigger` | `N` |

### Queue type

`param1` identifies the synchronization object:

| `param1` | Kind | BTF target | Send / receive |
|---:|---|---|---|
| 0 | Queue | `queue` | `send` / `recv` |
| 1 | Mutex | `mutex` | `give` / `take` |
| 2 | Counting semaphore | `sem` | `give` / `take` |
| 3 | Binary semaphore | `sem` | `give` / `take` |
| 4 | Recursive mutex | `mutex` | `give` / `take` |

## 10. Task identity and labels

`TASK_CREATE` writes the task name into the task table.

Task ids in BTF rows match:

```text
uxTCBNumber
```

Interval `param2` uses the same task id.

Task switch labels use:

```text
[core/id]Name
```

with a zero-padded four-digit task id, for example:

```text
[0/0007]CS
```

## 11. Limits and failure modes

| Area | Limit / behavior |
|---|---|
| SMP cores | `configNUMBER_OF_CORES` must be **1–31** |
| Ring capacity | Full ring overwrites oldest events |
| Task table | Out-of-range ids retain events but lose task names |
| Timestamp | 32-bit wrap is expected and extended offline |
| Truncation | Missing `traceEND()` or short binary dump produces `#truncated true` |

## 12. Decoder sanity checks

Decoder checks:

```text
1. Magic == BTF2
2. Endian tag == 1
3. Header is complete
4. Declared task/event regions fit the blob
5. event_count <= max_events
6. Ring replay order is reconstructed
7. 32-bit timestamps are extended across wraps
8. Core id is valid for num_cores
9. Event type is decoded
10. Quality metadata is emitted
```

For target-side requirements that produce this format, see **[PORTING.md](PORTING.md)**.
