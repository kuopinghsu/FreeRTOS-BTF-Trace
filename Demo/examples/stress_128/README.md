# 128-core synchronization stress test

Build only:

```sh
make -C Demo/examples CORES=128 \
  ../../build/demo/examples/cores128-tickless0/stress_128.elf
```

Build and run on the bundled simulator:

```sh
make -C Demo/examples stress_128
```

This target also rebuilds the simulator after a top-level `make clean`.
Trace capture is enabled by `configUSE_TRACE_FACILITY=1`. After a successful
run, the target dumps and converts the trace into:

```text
tracedata/stress-128-trace.bin  # raw trace buffer
tracedata/stress-128.btf        # BTFViewer input
tracedata/stress-128.vcd        # waveform viewer input
```

The default 80,000-event buffer is sufficient for this workload (a normal
four-round run currently emits about 13,600 events). Override it with
`MAX_TRACE_EVENTS=N` if the workload is expanded.

Do not compile `stress_128/main.c` with the default `CORES=1`: the test is
intentionally guarded so an accidental non-128-core build fails immediately.

The workload creates one task pinned to every core (including core 127), 128
work queues, one result queue, eight mutexes acquired in a globally ordered
pair, a 32-slot counting semaphore, and eight 16-worker event-group barriers.
Four rounds validate the executing core and returned work sequence.
Workers receive 384 stack words each; the controller receives 1024 because its
queue validation, event waits, and formatted progress output have a deeper call
path. Every completed round reports the controller stack high-water mark.
Each cohort also has a two-second simulated-time watchdog. On timeout, the
report includes the observed and missing event bits plus worker counts at each
stage (not started, job received, semaphore acquired, mutex work complete,
result queued, and event bit set), instead of hanging indefinitely.

Progress is flushed immediately during the long run. Output identifies object
creation, each batch of 16 created workers, scheduler startup, queued work,
each completed event-group cohort, result validation, and the PASS/FAIL status
of every round. For example:

```text
[stress128] boot: 128 cores, 4 rounds
[stress128] workers created: 16/128
...
[stress128] controller created; starting scheduler
[stress128] round 1/4: queued 128 jobs; waiting for cohorts
[stress128] round 1/4: cohort 1/8 complete
...
[stress128] round 1/4: PASS (failures=0, CTRL stack low-water=... words)
```

Before the first boot line, the simulator must initialize all harts and clear
the large trace buffer. That startup itself can take noticeable time in the
software simulator.

Software simulation of 128 harts is intentionally expensive. For CI, the ELF
build is the fast API/ABI check; run the full workload as a long-running stress
job or on the target platform.

The successful build verifies the 128-bit API surface, TCB/static-TCB layout,
core-127 mask construction, port arrays, and linkage. It does not by itself
qualify scheduler latency or prove completion under sustained 128-core
contention. The simulator may take many minutes per run.

BTF v1.4 records an 8-bit core ID, so cores 0–127 are representable. Its current
`TASK_SET_AFFINITY` payload is only 32 bits, however; the trace will truncate
affinity bits 32–127 until the trace format and BTFViewer parser are extended.
