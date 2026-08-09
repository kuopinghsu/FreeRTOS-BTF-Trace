# gentrace

Convert a firmware `trace.bin` dump to BTF or VCD.

```bash
gentrace dump.bin trace.btf     # BTF
gentrace -v dump.bin trace.vcd  # VCD
```

Binary layout and event → BTF field mapping: [`TRACE_FORMAT.md`](../TRACE_FORMAT.md).
