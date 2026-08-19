# FreeRTOS-BTF-Trace Format Reference

This document defines the `trace.bin` file layout, event encoding, BTF mapping, and trace-quality metadata.

| Document | Purpose |
|---|---|
| [README.md](README.md) | Build the demo, capture events, and open a trace |
| [PORTING.md](PORTING.md) | Integrate the trace library with another target |
| `FreeRTOS-Trace/btf_trace.h` | Review the C structures and `event_t` definitions |

## 1. File layout

`traceEND()` writes one little-endian binary blob. Its regions appear in this order:

| Region | Size |
|---|---:|
| `TRACE_HEADER` | 44 bytes |
| `task_lists` | `max_tasks × max_taskname_len` |
| `event_lists` | `max_events × 16` bytes |

Total file size:

```text
44 + max_tasks × max_taskname_len + max_events × 16
```

`traceSTART()` initializes the size fields from these configuration values:

| Binary field | Configuration |
|---|---|
| `max_tasks` | `configMAX_TRACE_TASKS` |
| `max_taskname_len` | `ALIGN4(configMAX_TRACE_TASK_NAME_LEN + 1)` |
| `max_events` | `configMAX_TRACE_EVENTS` |

## 2. Binary header

The header is 44 bytes and uses little-endian byte order.

| Offset | Field | Type | Meaning |
|---:|---|---|---|
| 0 | `header` | `char[4]` | Magic value `BTF2` |
| 4 | `tag` | `uint32_t` | Endian marker; must be `1` |
| 8 | `version` | `uint32_t` | `(major << 16) \| minor`; version 1.4 is `0x00010004` |
| 12 | `core_clock` | `uint32_t` | Counter frequency in Hz |
| 16 | `num_cores` | `uint32_t` | `configNUMBER_OF_CORES` |
| 20 | `max_tasks` | `uint32_t` | Number of task-name slots |
| 24 | `max_taskname_len` | `uint32_t` | Bytes in each aligned task-name slot |
| 28 | `max_events` | `uint32_t` | Event-ring capacity |
| 32 | `task_count` | `uint32_t` | Number of recorded `TASK_CREATE` events |
| 36 | `event_count` | `uint32_t` | Number of events currently retained |
| 40 | `current_index` | `uint32_t` | Next write index; points to the oldest event when the ring is full |

## 3. Task-name table

Each slot stores one NUL-terminated task name.

- The slot index is the FreeRTOS task ID, `uxTCBNumber`.
- The table is not a dense sequence from 0 through the number of active tasks.
- `traceTASK_CREATE` writes the task name.
- If `task_id == 0` or `task_id >= configMAX_TRACE_TASKS`, the event is retained without a task name.
- Export reports an unavailable task-name slot as `#taskTableOverflow true`.

## 4. Event record

Each event occupies 16 bytes.

| Offset | Field | Type | Meaning |
|---:|---|---|---|
| 0 | `timestamp` | `uint32_t` | Free-running cycle count |
| 4 | `param1` | `uint32_t` | First event-specific parameter |
| 8 | `param2` | `uint32_t` | Second event-specific parameter |
| 12 | `types` | `uint32_t` | `event_t` and optional core ID |

### `types` encoding

| Bits | Meaning |
|---|---|
| `[23:0]` | `event_t` |
| `[30:24]` | SMP core ID from `portGET_CORE_ID()` |
| `[31]` | Unused |

On a single-core build, `types` contains only the `event_t` value.

## 5. Event-ring ordering

Events are written at `current_index % max_events`.

- If `event_count < max_events`, replay records 0 through `event_count - 1`.
- If `event_count == max_events`, `current_index` identifies the oldest event.
- For a full ring, replay `current_index` through the end, then record 0 through `current_index - 1`.

After the ring wraps, each new event overwrites the oldest event. `event_count` remains equal to `max_events`, and the BTF export contains `#ringOverflow true`.

## 6. Timestamp reconstruction

`timestamp` comes from the free-running 32-bit `xGetCycles()` counter. Both `gentrace` and live `btf_dump()` reconstruct time as follows:

1. Detect a 2³² counter wrap.
2. Extend the counter to a monotonic 64-bit value.
3. Convert the value with `core_clock`.
4. Write the timestamp in the configured BTF time scale.

## 7. BTF quality metadata

A BTF export starts with the standard BTF metadata and may include these quality flags:

| Metadata | Meaning |
|---|---|
| `#ringOverflow true` | The event ring wrapped and the oldest events were lost |
| `#taskTableOverflow true` | At least one task ID had no task-name slot |
| `#truncated true` | `traceEND()` was not called, or `trace.bin` is shorter than a complete blob |

A clean trace omits these lines. The exporter infers the flags; they are not stored in the 44-byte binary header. BTFViewer displays a warning when any flag is present.

## 8. Convert binary data to BTF

`tools/gentrace` and live `btf_dump()` convert each binary event to one BTF 2.2.0 CSV line.

### 8.1 BTF file header

```text
#version 2.2.0
#creator FreeRTOS trace logger
#creationDate YYYY-MM-DDTHH:MM:SSZ
#timeScale us
```

Quality metadata follows this header when required. The exporter also creates one clock line for each core:

```text
<t>,Core_0,0,C,Core_0,0,set_frequency,<core_clock>
```

Clock lines are generated during export and are not stored in the event ring.

### 8.2 BTF event-line format

```text
time, source, 0, type, target, 0, action, note
```

Examples:

```text
214276,Core_0,0,STI,interval_start,0,trigger,0 tid:1
215514,Core_0,0,T,[0/0007]CS,0,resume,
217432,Core_1,0,STI,task,0,trigger,suspend SR0[271]
```

On SMP targets, the core ID comes from `types[30:24]`. It appears as `Core_N`, or as part of `[N/id]Name` for task-switch events.

## 9. Event mapping

| Event (`event_t`) | Hook or API | `param1` | `param2` | BTF type | Target | Action | Note |
|---|---|---|---|---|---|---|---|
| `TASK_SWITCHED_IN` (1) | `traceTASK_SWITCHED_IN` | task ID | 0 | `T` | `[core/id]Name` | `resume` | Empty; source is the previous task |
| `TASK_SWITCHED_OUT` (2) | `traceTASK_SWITCHED_OUT` | task ID | 0 | `T` | `[core/id]Name` | `preempt` | Empty |
| `TASK_CREATE` (3) | `traceTASK_CREATE` | task ID | priority | `T` | `[core/id]Name` | `preempt` | `create pri:N` |
| `TASK_DELETE` (4) | `traceTASK_DELETE` | task ID | 0 | `STI` | `task` | `trigger` | `delete Name[id]` |
| `TASK_SUSPEND` (5) | `traceTASK_SUSPEND` | task ID | 0 | `STI` | `task` | `trigger` | `suspend Name[id]` |
| `TASK_RESUME` (6) | `traceTASK_RESUME` | task ID | 0 | `STI` | `task` | `trigger` | `resume Name[id]` |
| `TASK_RESUME_FROM_ISR` (7) | `traceTASK_RESUME_FROM_ISR` | task ID | 0 | `STI` | `task` | `trigger` | `resume/isr` |
| `QUEUE_CREATE` (8) | `traceQUEUE_CREATE` | queue type | object pointer | `STI` | `queue`, `mutex`, or `sem` | `trigger` | `create 0x........` |
| `QUEUE_SEND` (9) | `traceQUEUE_SEND` | queue type | object pointer | `STI` | `queue`, `mutex`, or `sem` | `trigger` | send/give and address |
| `QUEUE_RECEIVE` (10) | `traceQUEUE_RECEIVE` | queue type | object pointer | `STI` | `queue`, `mutex`, or `sem` | `trigger` | recv/take and address |
| `QUEUE_DELETE` (11) | `traceQUEUE_DELETE` | queue type | object pointer | `STI` | `queue`, `mutex`, or `sem` | `trigger` | `delete 0x........` |
| `TASK_INCREMENT_TICK` (12) | `traceTASK_INCREMENT_TICK` | tick count | 0 | `STI` | `TICK` | `trigger` | `N` |
| `INTERVAL_START` (13) | `traceINTERVAL_START` | interval ID | caller task ID | `STI` | `interval_start` | `trigger` | `{id} tid:{task_id}` |
| `INTERVAL_STOP` (14) | `traceINTERVAL_STOP` | interval ID | caller task ID | `STI` | `interval_stop` | `trigger` | `{id} tid:{task_id}` |
| `TASK_PRIORITY_SET` (15) | `traceTASK_PRIORITY_SET` | task ID | new priority | `STI` | `task` | `trigger` | `set_priority Name[id] pri:N` |
| `TASK_PRIORITY_INHERIT` (16) | `traceTASK_PRIORITY_INHERIT` | holder ID | inherited priority | `STI` | `task` | `trigger` | `priority_inherit Name[id] pri:N` |
| `TASK_PRIORITY_DISINHERIT` (17) | `traceTASK_PRIORITY_DISINHERIT` | holder ID | base priority | `STI` | `task` | `trigger` | `priority_disinherit Name[id] pri:N` |
| `TASK_SET_AFFINITY` (18) | `traceENTER_vTaskCoreAffinitySet` | task ID | affinity mask | `STI` | `task` | `trigger` | `affinity_set Name[id] 0xMASK` |
| `TAG … TAG7` (90–97) | `traceTAG(t, v)` | tag value | 0 | `STI` | `tag0_event … tag7_event` | `trigger` | `N` |

### Queue type

`param1` identifies the synchronization object:

| `param1` | Object | BTF target | Send or receive |
|---:|---|---|---|
| 0 | Queue | `queue` | `send` / `recv` |
| 1 | Mutex | `mutex` | `give` / `take` |
| 2 | Counting semaphore | `sem` | `give` / `take` |
| 3 | Binary semaphore | `sem` | `give` / `take` |
| 4 | Recursive mutex | `mutex` | `give` / `take` |

## 10. Task identity and labels

`TASK_CREATE` writes the task name to the task table. Task IDs in BTF rows use `uxTCBNumber`. Interval `param2` uses the same ID.

Task-switch labels use this format:

```text
[core/id]Name
```

The task ID is padded to four digits:

```text
[0/0007]CS
```

## 11. Limits and failure modes

| Area | Limit or behavior |
|---|---|
| SMP cores | `configNUMBER_OF_CORES` must be from **1 through 31** |
| Event ring | A full ring overwrites the oldest events |
| Task table | Events with out-of-range IDs remain, but their task names are unavailable |
| Timestamp | A 32-bit wrap is expected and reconstructed during export |
| Truncation | A missing `traceEND()` call or short binary dump produces `#truncated true` |

## 12. Decoder checks

A decoder should validate the input in this order:

1. Confirm that the magic value is `BTF2`.
2. Confirm that the endian tag is `1`.
3. Confirm that the complete 44-byte header is present.
4. Confirm that the declared task and event regions fit within the file.
5. Confirm that `event_count <= max_events`.
6. Reconstruct the event-ring replay order.
7. Extend 32-bit timestamps across counter wraps.
8. Confirm that every core ID is valid for `num_cores`.
9. Decode the event type.
10. Add the required quality metadata.

See [PORTING.md](PORTING.md) for the target requirements that produce this format.
