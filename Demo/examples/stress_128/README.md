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

Do not compile `stress_128/main.c` with the default `CORES=1`: the test is
intentionally guarded so an accidental non-128-core build fails immediately.

The workload creates one task pinned to every core (including core 127), 128
work queues, one result queue, eight mutexes acquired in a globally ordered
pair, a 32-slot counting semaphore, and eight 16-worker event-group barriers.
Four rounds validate the executing core and returned work sequence.

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
