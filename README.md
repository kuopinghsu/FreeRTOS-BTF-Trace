# FreeRTOS-BTF-Trace

[![Codacy Badge](https://app.codacy.com/project/badge/Grade/f952ae549fe94c2b88401a2cf935359b)](https://www.codacy.com/gh/kuopinghsu/FreeRTOS-BTF-Trace/dashboard?utm_source=github.com&amp;utm_medium=referral&amp;utm_content=kuopinghsu/FreeRTOS-BTF-Trace&amp;utm_campaign=Badge_Grade)

Generate BTF trace file for FreeRTOS.

BTF (Best Trace Format) is a CSV-based format used to record and trace at the system
level to analyze the timing, performance, and reliability of embedded real-time systems.
The spec can be found [here](https://assets.vector.com/cms/content/products/TA_Tool_Suite/Docs/BTF_Specification.pdf).

Tracelyzer from [Percepio](https://percepio.com/tracealyzer/) is the best analysis tools to visualize the real-time execution of tasks and ISRs. Sometimes we only need a simple solution to see the execution of the task and find the performance bottleneck. The project provides a simple and extensible framework for this, and most importantly, it is open source and free. There's another solution is using [BareCTF](https://barectf.org/) and [Trace Compass](https://www.eclipse.org/tracecompass/) to trace FreeRTOS system in [freerots-barectf](https://github.com/gpollo/freertos-barectf).

## Build

This is an example to test <A Href="https://github.com/kuopinghsu/srv32">srv32</A> on FreeRTOS. The code can be run on the ISS (Instruction Set Simulator) of srv32 to generate trace data in BTF format. This can be easily ported to another platform.

Requirement: Install the toolchains. See details in srv32 <A Href="https://github.com/kuopinghsu/srv32#building-toolchains">Building toolchains</A> section.

Calling traceSTART() to enable trace, and calling traceEND() to stop trace and dump data to memory.

    $ make run

The file "trace.btf" will be generated under Demo/examples folder. Open it by the Trace Compass.

## Trace Compass

This is a screen shot of <a href="https://www.eclipse.org/tracecompass/"> Trace Compass </a>
by reading the BTF trace file

<img src="images/trace-compass.png" alt="trace-compass" width=640>

## Porting guide

1.  Include FreeRTOS-Trace/FreeRTOS-Trace.h in your FreeRTOSConfig.h.
2.  Provide xGetTime() macro in FreeRTOS-Trace/btf_port.h to report the system time in nanoseconds.
3.  Keep HAVE_SYS_DUMP undefined in FreeRTOS-Trace/btf_port.h.
4.  Compile the code FreeRTOS-Trace/btf_trace.c with your project.
5.  Call traceSTART() in your application to enable trace log.
```c
#if configUSE_TRACE_FACILITY
    traceSTART();
#endif
```
6.  Call traceEND() in your application to disable trace log.
```c
#if configUSE_TRACE_FACILITY
    traceEND();
#endif
```
7.  After the application is built, use readelf to find the location of trace_data. Run the application and dump the memory to a binary file. In this example, you should dump 65572 bytes of data from address 0x21d44.
```c
$ readelf -a task.elf
...
21: 00021d44 65572 OBJECT  LOCAL  DEFAULT    4 trace_data
...
```
8.  Using gentrace tools to convert trace data to BTF file.
```
$ ../../tools/gentrace dump.bin trace.btf
814 events generated
```
9.  Open the BTF file with Trace Compass to view the trace file.

## License

MIT license

