# FreeRTOS-BTF-Trace

[![Codacy Badge](https://app.codacy.com/project/badge/Grade/f952ae549fe94c2b88401a2cf935359b)](https://www.codacy.com/gh/kuopinghsu/FreeRTOS-BTF-Trace/dashboard?utm_source=github.com&amp;utm_medium=referral&amp;utm_content=kuopinghsu/FreeRTOS-BTF-Trace&amp;utm_campaign=Badge_Grade)

Generate BTF trace file for FreeRTOS.

BTF (Best Trace Format) is a CSV-based format used to record and trace at the system
level to analyze the timing, performance, and reliability of embedded real-time systems.
The spec can be found <a href="https://assets.vector.com/cms/content/products/TA_Tool_Suite/Docs/BTF_Specification.pdf"> here </a>

## Build

This is an example to test <A Href="https://github.com/kuopinghsu/srv32">srv32</A> on FreeRTOS. The code can be run on the ISS (Instruction Set Simulator) of srv32 to generate trace data in BTF format. This can be easily ported to another platform.

Requirement: Install the toolchains. See details in srv32 <A Href="https://github.com/kuopinghsu/srv32#building-toolchains">Building toolchains</A> section.

Calling traceSTART() to enable trace, and calling traceEND() to stop trace and dump data to memory.

    $ make run

The file "trace.btf" will be generated under Demo/examples folder. Open it by the Trace Compass.

## Trace Compass

This is a screenshot of <a href="https://www.eclipse.org/tracecompass/"> Trace Compass </a>
by reading the BTF trace file

<img src="images/trace-compass.png" alt="trace-compass" width=640>

## Porting guide

1.  Include Demo/trace/FreeRTOS-Trace.h in your FreeRTOSConfig.h.
2.  Provide xGetTime() macro in Demo/trace/port.h to report the system time in nano seconds.
3.  Compile the code Demo/trace/btf_trace.c with your project.

## License

MIT license
