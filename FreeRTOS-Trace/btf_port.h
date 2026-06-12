// Copyright (c) 2021 Kuoping Hsu
//
// Permission is hereby granted, free of charge, to any person obtaining a copy
// of this software and associated documentation files (the "Software"), to deal
// in the Software without restriction, including without limitation the rights
// to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
// copies of the Software, and to permit persons to whom the Software is
// furnished to do so, subject to the following conditions:
//
// The above copyright notice and this permission notice shall be included in all
// copies or substantial portions of the Software.
//
// THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
// IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
// FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
// AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
// LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
// OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
// SOFTWARE.

#ifndef __PORT_H__
#define __PORT_H__

#include <stdint.h>

#ifdef __riscv
#ifndef portGET_RUN_TIME_COUNTER_VALUE
#define portGET_RUN_TIME_COUNTER_VALUE() ({uint32_t cycles; asm volatile ("rdcycle %0" : "=r"(cycles)); cycles; })
#endif

// get runtime cycles
#define xGetCycles() portGET_RUN_TIME_COUNTER_VALUE()

#define HAVE_FILE_DUMP
//#define PRINT_BTF_DUMP

/*
 * Live stdout BTF dump: uncomment PRINT_BTF_DUMP to call btf_dump() at traceEND().
 * Output is BTF 2.2.0 CSV on stdout (redirect to a file or pipe to a viewer).
 *
 * TIMESCALE_US - only used when PRINT_BTF_DUMP is defined. Selects the unit written
 * in the #timeScale header and used when converting raw CPU cycles to timestamps:
 *   1 (default) -> microseconds  (#timeScale us)
 *   0           -> nanoseconds   (#timeScale ns)
 * Conversion uses configCPU_CLOCK_HZ from FreeRTOSConfig.h. Override before including
 * this header if needed, e.g. in FreeRTOSConfig.h:
 *   #define TIMESCALE_US 0
 *   #include "FreeRTOS-Trace/FreeRTOS-Trace.h"
 */
#ifdef PRINT_BTF_DUMP
#ifndef TIMESCALE_US
#define TIMESCALE_US  1
#endif
#endif

#ifndef TRACE_DUMP_FILENAME
#define TRACE_DUMP_FILENAME "trace.bin"
#endif

#else

#error "needs to implement the xGetCycles() API"

#define xGetCycles() 0
#undef HAVE_FILE_DUMP
#undef PRINT_BTF_DUMP

#endif

#endif // __PORT_H__
