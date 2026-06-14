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

#include "freertos_risc_v_chip_specific_extensions.h"

/*
 * xGetCycles() — platform hook that stamps each trace event with a raw counter.
 *
 * Contract (all ports):
 *   - Return type is uint32_t only.  trace.bin stores EVENT.timestamp as 32
 *     bits so the on-target format stays the same on every platform (mtime,
 *     DWT cycle counter, GPT tick, etc.).
 *   - The counter may wrap at 2^32; firmware does not extend it to 64 bits.
 *
 * Wrap handling (offline, not in firmware):
 *   tools/gentrace and btf_dump() rebuild monotonic BTF times in cyc_to_time():
 *   when a raw timestamp is less than the previous one, one full 2^32 period
 *   is added to an accumulator, then the value is scaled to us/ns using
 *   trace_data.h.core_clock (same as configCPU_CLOCK_HZ on target).
 *
 * This demo reads the lower 32 bits of CLINT mtime.  In riscv64-sim, mtime is a
 * global fixed-rate clock (one tick per simulator cycle), not a retired-instruction
 * count and not multiplied by the number of cores.
 */
#ifndef portGET_RUN_TIME_COUNTER_VALUE
#define portGET_RUN_TIME_COUNTER_VALUE() \
    ( *( volatile uint32_t * ) ( uintptr_t ) configMTIME_BASE_ADDRESS )
#endif

#define xGetCycles()    portGET_RUN_TIME_COUNTER_VALUE()

#define HAVE_FILE_DUMP
//#define PRINT_BTF_DUMP

/*
 * Live stdout BTF dump: uncomment PRINT_BTF_DUMP to call btf_dump() at traceEND().
 * Output is BTF 2.2.0 CSV on stdout (redirect to a file or pipe to a viewer).
 *
 * TIMESCALE_US - only used when PRINT_BTF_DUMP is defined. Selects the unit written
 * in the #timeScale header and used when converting raw mtime counts to timestamps:
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

/*
 * Port xGetCycles() for your target: must return a free-running uint32_t counter.
 * Timer wrap at 2^32 is normal; gentrace / btf_dump extend it when building BTF.
 */
#error "needs to implement the xGetCycles() API"

#define xGetCycles() 0
#undef HAVE_FILE_DUMP
#undef PRINT_BTF_DUMP

#endif

#endif // __PORT_H__
