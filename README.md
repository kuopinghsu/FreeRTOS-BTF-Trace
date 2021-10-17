# FreeRTOS-BTF-Trace
Generate BTF trace file for FreeRTOS.

BTF (Best Trace Format) is a CSV-based format used to record and trace at the system
level to analyze the timing, performance, and reliability of embedded real-time systems.
The spec can be found <a href="https://assets.vector.com/cms/content/products/TA_Tool_Suite/Docs/BTF_Specification.pdf"> here </a>

## Run

This is an example to test <A Href="https://github.com/kuopinghsu/srv32">srv32</A> on FreeRTOS. The code can be run on the ISS (Instruction Set Simulator) of srv32 to generate trace data in BTF format. This can be easily ported to another platform.

Requirement: Install the toolchains. See details in srv32 <A Href="https://github.com/kuopinghsu/srv32#building-toolchains">Building toolchains</A> section.

```
$ make run
```

The file "trace.btf" will be generated under Demo/examples folder. Open it by the Trace Compass.

## Result
<img src="images/trace-compass.png" alt="trace-compass" width=640>

## Porting guide

TBD

## License
GPL-v3 license
