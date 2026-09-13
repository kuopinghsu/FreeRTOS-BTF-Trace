# FreeRTOS 128-core affinity patch

`freertos-kernel-v11.3.1-128-core-affinity.patch` applies to the official
FreeRTOS-Kernel V11.3.1 tag.

Apply it from a FreeRTOS-Kernel checkout:

```sh
git checkout V11.3.1
git apply ../patches/freertos-kernel-v11.3.1-128-core-affinity.patch
```

The patch introduces `TaskCoreAffinityMask_t` and
`taskCORE_AFFINITY_BIT(core)`. Existing affinity APIs keep their names but use
the new mask type:

```c
TaskCoreAffinityMask_t mask = taskCORE_AFFINITY_BIT( 0 ) |
                              taskCORE_AFFINITY_BIT( 127 );
xTaskCreateAffinitySet( task, "worker", stack, arg, priority, mask, &handle );
vTaskCoreAffinitySet( handle, mask );
mask = vTaskCoreAffinityGet( handle );
```

For 1–32 cores the type remains `UBaseType_t`; 33–64 cores use `uint64_t`;
65–128 cores use the compiler's 128-bit unsigned integer. A port can override
`portTASK_CORE_AFFINITY_TYPE`. The supplied implementation therefore requires
GCC/Clang `__int128` support above 64 cores unless the port supplies a compatible
integer-like 128-bit type.

## Compatibility and current limitations

- This is an experimental downstream patch. FreeRTOS V11.3.1 and current
  upstream `main` still use `UBaseType_t` for affinity and do not officially
  support a 128-bit affinity mask.
- The affinity API and TCB ABI change when `configNUMBER_OF_CORES > 32`. Rebuild
  the kernel, port, application, trace hooks, static-task storage, and any
  kernel-aware debugger together. Mixing objects built against different mask
  widths is unsupported.
- `StaticTask_t` is widened together with the internal TCB. This is required for
  `xTaskCreateStatic()` and the kernel-created Idle tasks to pass their layout
  checks.
- The existing BTF v1.4 affinity event carries only 32 mask bits. Core IDs up to
  127 remain encodable, but affinity bits 32–127 are truncated in
  `affinity_set` events. Full-width affinity tracing requires a new trace-format
  record and viewer support.
- `vTaskList()` currently formats the affinity value through an `unsigned int`,
  so its textual affinity column also shows only the low 32 bits.
- The bundled RV64 simulator accepts 128 harts and the stress ELF compiles and
  links. Full stress completion is extremely slow under software simulation and
  is not yet evidence of production-qualified 128-core scheduling scalability.
- Scheduler paths still contain linear core scans and shared scheduler locks.
  Functional mask width does not guarantee acceptable latency or contention on
  a physical 128-core system.

For a fast verification, compile the ELF without starting the simulator:

```sh
make -C Demo/examples CORES=128 \
  ../../build/demo/examples/cores128-tickless0/stress_128.elf
```
