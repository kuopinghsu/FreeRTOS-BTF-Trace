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

#include <stdio.h>
#include <stdint.h>
#include <inttypes.h>
#include <assert.h>
#include "FreeRTOS.h"
#include "btf_trace.h"
#include "task.h"

// Packed event-word bit-field layout (32 bits): [31:24] core ID, [23:0] btf_event_t value.
#define EVENT_MASK      0x00ffffffu
#define EVENT_SHIFT     0
#define COREID_MASK     0x7f000000u
#define COREID_SHIFT    24

// Example of __DATE__ string: "Jul 27 2012"
//                              01234567890
#define BUILD_YEAR  ((__DATE__[ 7]-'0') * 1000 + (__DATE__[ 8]-'0') * 100+\
                     (__DATE__[ 9]-'0') * 10   + (__DATE__[10]-'0'))

#define BUILD_MONTH ( \
                     (__DATE__[0] == 'J' && __DATE__[1] == 'a' && __DATE__[2] == 'n') ? 1 : \
                     (__DATE__[0] == 'F')                                             ? 2 : \
                     (__DATE__[0] == 'M' && __DATE__[1] == 'a' && __DATE__[2] == 'r') ? 3 : \
                     (__DATE__[0] == 'A' && __DATE__[1] == 'p')                       ? 4 : \
                     (__DATE__[0] == 'M' && __DATE__[1] == 'a' && __DATE__[2] == 'y') ? 5 : \
                     (__DATE__[0] == 'J' && __DATE__[1] == 'u' && __DATE__[2] == 'n') ? 6 : \
                     (__DATE__[0] == 'J' && __DATE__[1] == 'u' && __DATE__[2] == 'l') ? 7 : \
                     (__DATE__[0] == 'A' && __DATE__[1] == 'u')                       ? 8 : \
                     (__DATE__[0] == 'S')                                             ? 9 : \
                     (__DATE__[0] == 'O')                                             ? 10 : \
                     (__DATE__[0] == 'N')                                             ? 11 : \
                     (__DATE__[0] == 'D')                                             ? 12 : \
                                                                                        99)

#define BUILD_DAY   ((((__DATE__[4] >= '0') ? (__DATE__[4]) : '0') - '0') * 10 \
                    + (__DATE__[ 5]) - '0')

// Example of __TIME__ string: "21:06:19"
//                              01234567
#define BUILD_HOUR ((__TIME__[0] - '0') * 10 + (__TIME__[1] - '0'))
#define BUILD_MIN  ((__TIME__[3] - '0') * 10 + (__TIME__[4] - '0'))
#define BUILD_SEC  ((__TIME__[6] - '0') * 10 + (__TIME__[7] - '0'))

#if configUSE_TRACE_FACILITY

#include "btf_port.h"

static volatile uint32_t trace_en;
static TRACE trace_data;
static int trace_wrap_warned;
static uint32_t trace_last_tick;
static int trace_last_tick_valid;

static uint32_t last_timestamp;
static uint64_t cyc_to_time_acc;

void btf_traceSTART(void) {
    trace_en = 1;
    trace_data.h.header[0] = 'B';
    trace_data.h.header[1] = 'T';
    trace_data.h.header[2] = 'F';
    trace_data.h.header[3] = '2';
    trace_data.h.tag = 1;
    trace_data.h.version = TRACE_VERSION;
    trace_data.h.core_clock = configCPU_CLOCK_HZ;
    trace_data.h.num_cores = configNUMBER_OF_CORES;
    trace_data.h.max_tasks = configMAX_TRACE_TASKS;
    trace_data.h.max_taskname_len = ALIGN4(configMAX_TRACE_TASK_NAME_LEN+1);
    trace_data.h.max_events = configMAX_TRACE_EVENTS;
    trace_data.h.task_count = 0;
    trace_data.h.event_count = 0;
    trace_data.h.current_index = 0;

    last_timestamp = 0;
    cyc_to_time_acc = 0;
    trace_wrap_warned = 0;
    trace_last_tick_valid = 0;
}

void btf_traceEND(void) {
    trace_en = 0;

#ifdef HAVE_FILE_DUMP
    do {
        FILE *fp = fopen(TRACE_DUMP_FILENAME, "wb");
        if (fp) {
            fwrite(&trace_data, 1, sizeof(trace_data), fp);
            fclose(fp);
        }
    } while (0);
#endif
#ifdef PRINT_BTF_DUMP
    btf_dump();
#endif

    printf("%" PRIu32 " events generated.\n", trace_data.h.event_count);
}

void btf_traceTAG(int t, int v) {
    t &= 7; // limit to 0 .. 7
    btf_trace_add_event((uint32_t)v, 0, (event_t)(TRACE_EVENT_TAG + t));
}

static uint32_t btf_trace_current_task_id(void)
{
    TaskHandle_t h = xTaskGetCurrentTaskHandle();

    if (h != NULL) {
        return (uint32_t)uxTaskGetTaskNumber(h);
    }
    return 0;
}

void btf_traceINTERVAL_START(int id) {
    btf_trace_add_event((uint32_t)id, btf_trace_current_task_id(), TRACE_EVENT_INTERVAL_START);
}

void btf_traceINTERVAL_STOP(int id) {
    btf_trace_add_event((uint32_t)id, btf_trace_current_task_id(), TRACE_EVENT_INTERVAL_STOP);
}

void btf_trace_add_task (
    uint8_t *task_name,
    uint32_t task_id,
    uint32_t priority,
    event_t  event)
{
    int i;
    if (!trace_en) { return; }

    // task_id is a unique ID, which will increase by 1 each time a TCB is created.
    // Copy task name with a local loop instead of strncpy() to avoid pulling in
    // libc string helpers in the FreeRTOS firmware build.
    i = 0;
    while( i < ( configMAX_TRACE_TASK_NAME_LEN - 1 ) && task_name[ i ] != 0 )
    {
        trace_data.d.task_lists[ task_id ][ i ] = task_name[ i ];
        i++;
    }
    trace_data.d.task_lists[ task_id ][ i ] = 0;
    trace_data.h.task_count++;

    trace_data.d.event_lists[trace_data.h.current_index].timestamp = xGetCycles();
    trace_data.d.event_lists[trace_data.h.current_index].param1 = task_id;
    trace_data.d.event_lists[trace_data.h.current_index].param2 = priority;

#if configNUMBER_OF_CORES == 1
    trace_data.d.event_lists[trace_data.h.current_index].types = event;
#else
    trace_data.d.event_lists[trace_data.h.current_index].types =  (((uint32_t)(event) << EVENT_SHIFT) & EVENT_MASK) |
                                     ((portGET_CORE_ID() << COREID_SHIFT) & COREID_MASK);
#endif

    trace_data.h.current_index++;
    if (trace_data.h.current_index == configMAX_TRACE_EVENTS) {
        trace_data.h.current_index = 0;
        if (!trace_wrap_warned) {
            trace_wrap_warned = 1;
            printf("\nWarning: trace data wrap, only last events will be recorded.\n");
        }
    }
    if (trace_data.h.event_count < configMAX_TRACE_EVENTS) {
        trace_data.h.event_count++;
    }
}

void btf_trace_add_event (
    uint32_t param1,
    uint32_t param2,
    event_t  event)
{
    if (!trace_en) { return; }

    trace_data.d.event_lists[trace_data.h.current_index].timestamp = xGetCycles();
    trace_data.d.event_lists[trace_data.h.current_index].param1 = param1;
    trace_data.d.event_lists[trace_data.h.current_index].param2 = param2;

#if configNUMBER_OF_CORES == 1
    trace_data.d.event_lists[trace_data.h.current_index].types = event;
#else
    trace_data.d.event_lists[trace_data.h.current_index].types =  (((uint32_t)(event) << EVENT_SHIFT) & EVENT_MASK) |
                                     ((portGET_CORE_ID() << COREID_SHIFT) & COREID_MASK);
#endif

    trace_data.h.current_index++;
    if (trace_data.h.current_index == configMAX_TRACE_EVENTS) {
        trace_data.h.current_index = 0;
        if (!trace_wrap_warned) {
            trace_wrap_warned = 1;
            printf("\nWarning: trace data wrap, only last events will be recorded.\n");
        }
    }
    if (trace_data.h.event_count < configMAX_TRACE_EVENTS) {
        trace_data.h.event_count++;
    }
}

void btf_trace_increment_tick (
    uint32_t xTickCount)
{
    UBaseType_t uxSavedInterruptStatus;

    if (!trace_en) { return; }

    /* Official FreeRTOS calls traceTASK_INCREMENT_TICK() before xTickCount is
     * updated.  While the scheduler is suspended, core 0 may still take timer
     * IRQs; each call passes the same xTickCount.  Drop those duplicates here
     * so BTF has one STI TICK line per tick-number step. */
    if (trace_last_tick_valid && trace_last_tick == xTickCount) {
        return;
    }

    trace_last_tick = xTickCount;
    trace_last_tick_valid = 1;

    uxSavedInterruptStatus = taskENTER_CRITICAL_FROM_ISR();
    btf_trace_add_event(xTickCount, 0, TRACE_EVENT_TASK_INCREMENT_TICK);
    taskEXIT_CRITICAL_FROM_ISR( uxSavedInterruptStatus );
}

#ifdef PRINT_BTF_DUMP

#ifndef TIMESCALE_US
#define TIMESCALE_US  1
#endif
#if TIMESCALE_US == 1
#define TIMESCALE     1000000LL
#else
#define TIMESCALE     1000000000LL
#endif

#define get_taskname(n,i) n.d.task_lists[i]
#define get_event(n,i) (&n.d.event_lists[i])

// Reconstruct monotonic BTF time from xGetCycles() 32-bit raw stamps (wrap at 2^32).
static uint64_t cyc_to_time(uint32_t timestamp) {
    if (timestamp < last_timestamp) {
        cyc_to_time_acc += ((uint64_t)(UINT32_MAX) + 1) * TIMESCALE / configCPU_CLOCK_HZ;
    }

    last_timestamp = timestamp;

    return ((uint64_t)timestamp * TIMESCALE / configCPU_CLOCK_HZ) + cyc_to_time_acc;
}

void btf_dump(
    void) {
    int i;
    int current_task[configNUMBER_OF_CORES];
    int current_index;
    uint64_t current_time;
    EVENT *event;

    last_timestamp = 0;
    cyc_to_time_acc = 0;

    // Check header
    if (trace_data.h.header[0] != 'B' ||
        trace_data.h.header[1] != 'T' ||
        trace_data.h.header[2] != 'F' ||
        trace_data.h.header[3] != '2') {
        printf("The header of trace data is not correct.\n");
        return;
    }

    printf("\n");
    printf("#version 2.2.0\n");
    printf("#creator FreeRTOS trace logger\n");

    // Timestamp of the start of simulation or measurement. The format has to comply
    // with "ISO 8601 extended specification for representations of dates and times"
    // YYYY-MMDDTHH:MM:SS. The time should be in UTC time (indicated by a "Z" at the
    // end)
    printf("#creationDate %04d-%02d-%02dT%02d:%02d:%02dZ\n", BUILD_YEAR, BUILD_MONTH,
           BUILD_DAY, BUILD_HOUR, BUILD_MIN, BUILD_SEC);

#if TIMESCALE_US == 1
    printf("#timeScale us\n");
#else
    printf("#timeScale ns\n");
#endif

    if (trace_data.h.event_count != trace_data.h.max_events)
        current_index = 0;
    else
        current_index = trace_data.h.current_index;

    event = get_event(trace_data, current_index);

    current_time = cyc_to_time(event->timestamp);

    // Emit an initial clock-frequency event for each core.
    for(i=0; i < configNUMBER_OF_CORES; i++) {
        printf("%" PRIu64 ",Core_%d,0,C,Core_%d,0,set_frequency,%" PRIu32 "\n",
                current_time, i, i, trace_data.h.core_clock);
    }

    // Initialize per-core "current task" tracking;
    for(i=0; i < configNUMBER_OF_CORES; i++) {
        current_task[i] = 0;
    }

    for(i = 0; i < trace_data.h.event_count; i++) {
        event = get_event(trace_data, current_index);
#if configNUMBER_OF_CORES == 1
        int coreid = 0;
#else
        int coreid = ((int)(event->types & COREID_MASK)) >> COREID_SHIFT;
#endif
        current_time = cyc_to_time(event->timestamp);

        switch(event->types & EVENT_MASK) {
            case TRACE_EVENT_TASK_SWITCHED_IN:
                printf( "%" PRIu64 ",[%d/%04d]%s,0,T,[%d/%04" PRIu32 "]%s,0,%s,%s\n",
                        current_time,
                        coreid,
                        current_task[coreid], get_taskname(trace_data, current_task[coreid]),
                        coreid,
                        event->param1, get_taskname(trace_data, event->param1),
                        "resume",
                        "");
                break;
            case TRACE_EVENT_TASK_SWITCHED_OUT:
                printf( "%" PRIu64 ",Core_%d,0,T,[%d/%04" PRIu32 "]%s,0,%s,%s\n",
                        current_time,
                        coreid,
                        coreid,
                        event->param1, get_taskname(trace_data, event->param1),
                        "preempt",
                        "");
                current_task[coreid] = (int)event->param1;
                break;
            case TRACE_EVENT_TASK_CREATE:
                printf( "%" PRIu64 ",Core_%d,0,T,[%d/%04" PRIu32 "]%s,0,%s,%s pri:%d\n",
                        current_time,
                        coreid,
                        coreid,
                        event->param1, get_taskname(trace_data, event->param1),
                        "preempt",
                        "create",
                        event->param2);
                break;
            case TRACE_EVENT_TASK_DELETE:
                printf( "%" PRIu64 ",Core_%d,0,STI,%s,0,%s,%s %s[%d]\n",
                        current_time,
                        coreid,
                        "task",
                        "trigger",
                        "delete",
                        get_taskname(trace_data, event->param1),
                        (int)event->param1);
                break;
            case TRACE_EVENT_TASK_SUSPEND:
                printf( "%" PRIu64 ",Core_%d,0,STI,%s,0,%s,%s %s[%d]\n",
                        current_time,
                        coreid,
                        "task",
                        "trigger",
                        "suspend",
                        get_taskname(trace_data, event->param1),
                        (int)event->param1);
                break;
            case TRACE_EVENT_TASK_RESUME:
                printf( "%" PRIu64 ",Core_%d,0,STI,%s,0,%s,%s %s[%d]\n",
                        current_time,
                        coreid,
                        "task",
                        "trigger",
                        "resume",
                        get_taskname(trace_data, event->param1),
                        (int)event->param1);
                break;
            case TRACE_EVENT_TASK_RESUME_FROM_ISR:
                printf( "%" PRIu64 ",Core_%d,0,STI,%s,0,%s,%s\n",
                        current_time,
                        coreid,
                        "task",
                        "trigger",
                        "resume/isr");
                break;
            case TRACE_EVENT_TASK_PRIORITY_SET:
                printf( "%" PRIu64 ",Core_%d,0,STI,%s,0,%s,%s %s[%d] pri:%d\n",
                        current_time,
                        coreid,
                        "task",
                        "trigger",
                        "set_priority",
                        get_taskname(trace_data, event->param1),
                        (int)event->param1,
                        (int)event->param2);
                break;
            case TRACE_EVENT_QUEUE_CREATE:
                switch(event->param1) {
                case QUEUE_TYPE_MUTEX:
                case QUEUE_TYPE_RECURSIVE_MUTEX:
                    printf( "%" PRIu64 ",Core_%d,0,STI,%s,0,%s,%s 0x%08x\n",
                            current_time,
                            coreid,
                            "mutex",
                            "trigger",
                            "create",
                            event->param2);
                    break;
                case QUEUE_TYPE_COUNTING_SEM:
                case QUEUE_TYPE_BINARY_SEM:
                    printf( "%" PRIu64 ",Core_%d,0,STI,%s,0,%s,%s 0x%08x\n",
                            current_time,
                            coreid,
                            "sem",
                            "trigger",
                            "create",
                            event->param2);
                    break;
                default:
                    printf( "%" PRIu64 ",Core_%d,0,STI,%s,0,%s,%s 0x%08x\n",
                            current_time,
                            coreid,
                            "queue",
                            "trigger",
                            "create",
                            event->param2);
                }
                break;
            case TRACE_EVENT_QUEUE_SEND:
                switch(event->param1) {
                case QUEUE_TYPE_MUTEX:
                case QUEUE_TYPE_RECURSIVE_MUTEX:
                    printf( "%" PRIu64 ",Core_%d,0,STI,%s,0,%s,%s 0x%08x\n",
                            current_time,
                            coreid,
                            "mutex",
                            "trigger",
                            "give",
                            event->param2);
                    break;
                case QUEUE_TYPE_COUNTING_SEM:
                case QUEUE_TYPE_BINARY_SEM:
                    printf( "%" PRIu64 ",Core_%d,0,STI,%s,0,%s,%s 0x%08x\n",
                            current_time,
                            coreid,
                            "sem",
                            "trigger",
                            "give",
                            event->param2);
                    break;
                default:
                    printf( "%" PRIu64 ",Core_%d,0,STI,%s,0,%s,%s 0x%08x\n",
                            current_time,
                            coreid,
                            "queue",
                            "trigger",
                            "send",
                            event->param2);
                }
                break;
            case TRACE_EVENT_QUEUE_RECEIVE:
                switch(event->param1) {
                case QUEUE_TYPE_MUTEX:
                case QUEUE_TYPE_RECURSIVE_MUTEX:
                    printf( "%" PRIu64 ",Core_%d,0,STI,%s,0,%s,%s 0x%08x\n",
                            current_time,
                            coreid,
                            "mutex",
                            "trigger",
                            "take",
                            event->param2);
                    break;
                case QUEUE_TYPE_COUNTING_SEM:
                case QUEUE_TYPE_BINARY_SEM:
                    printf( "%" PRIu64 ",Core_%d,0,STI,%s,0,%s,%s 0x%08x\n",
                            current_time,
                            coreid,
                            "sem",
                            "trigger",
                            "take",
                            event->param2);
                    break;
                default:
                    printf( "%" PRIu64 ",Core_%d,0,STI,%s,0,%s,%s 0x%08x\n",
                            current_time,
                            coreid,
                            "queue",
                            "trigger",
                            "recv",
                            event->param2);
                }
                break;
            case TRACE_EVENT_QUEUE_DELETE:
                switch(event->param1) {
                case QUEUE_TYPE_MUTEX:
                case QUEUE_TYPE_RECURSIVE_MUTEX:
                    printf( "%" PRIu64 ",Core_%d,0,STI,%s,0,%s,%s 0x%08x\n",
                            current_time,
                            coreid,
                            "mutex",
                            "trigger",
                            "delete",
                            event->param2);
                    break;
                case QUEUE_TYPE_COUNTING_SEM:
                case QUEUE_TYPE_BINARY_SEM:
                    printf( "%" PRIu64 ",Core_%d,0,STI,%s,0,%s,%s 0x%08x\n",
                            current_time,
                            coreid,
                            "sem",
                            "trigger",
                            "delete",
                            event->param2);
                    break;
                default:
                    printf( "%" PRIu64 ",Core_%d,0,STI,%s,0,%s,%s 0x%08x\n",
                            current_time,
                            coreid,
                            "queue",
                            "trigger",
                            "delete",
                            event->param2);
                }
                break;
            case TRACE_EVENT_TASK_INCREMENT_TICK:
                printf( "%" PRIu64 ",Core_%d,0,STI,%s,0,%s,%" PRIu32 "\n",
                        current_time,
                        coreid,
                        "TICK",
                        "trigger",
                        event->param1);
                break;
            case TRACE_EVENT_INTERVAL_START:
                printf( "%" PRIu64 ",Core_%d,0,STI,%s,0,%s,%" PRIu32 " tid:%" PRIu32 "\n",
                        current_time,
                        coreid,
                        "interval_start",
                        "trigger",
                        event->param1,
                        event->param2);
                break;
            case TRACE_EVENT_INTERVAL_STOP:
                printf( "%" PRIu64 ",Core_%d,0,STI,%s,0,%s,%" PRIu32 " tid:%" PRIu32 "\n",
                        current_time,
                        coreid,
                        "interval_stop",
                        "trigger",
                        event->param1,
                        event->param2);
                break;
            case TRACE_EVENT_TAG:
                printf( "%" PRIu64 ",Core_%d,0,STI,%s,0,%s,%" PRIu32 "\n",
                        current_time,
                        coreid,
                        "tag0_event",
                        "trigger",
                        event->param1);
                break;
            case TRACE_EVENT_TAG1:
                printf( "%" PRIu64 ",Core_%d,0,STI,%s,0,%s,%" PRIu32 "\n",
                        current_time,
                        coreid,
                        "tag1_event",
                        "trigger",
                        event->param1);
                break;
            case TRACE_EVENT_TAG2:
                printf( "%" PRIu64 ",Core_%d,0,STI,%s,0,%s,%" PRIu32 "\n",
                        current_time,
                        coreid,
                        "tag2_event",
                        "trigger",
                        event->param1);
                break;
            case TRACE_EVENT_TAG3:
                printf( "%" PRIu64 ",Core_%d,0,STI,%s,0,%s,%" PRIu32 "\n",
                        current_time,
                        coreid,
                        "tag3_event",
                        "trigger",
                        event->param1);
                break;
            case TRACE_EVENT_TAG4:
                printf( "%" PRIu64 ",Core_%d,0,STI,%s,0,%s,%" PRIu32 "\n",
                        current_time,
                        coreid,
                        "tag4_event",
                        "trigger",
                        event->param1);
                break;
            case TRACE_EVENT_TAG5:
                printf( "%" PRIu64 ",Core_%d,0,STI,%s,0,%s,%" PRIu32 "\n",
                        current_time,
                        coreid,
                        "tag5_event",
                        "trigger",
                        event->param1);
                break;
            case TRACE_EVENT_TAG6:
                printf( "%" PRIu64 ",Core_%d,0,STI,%s,0,%s,%" PRIu32 "\n",
                        current_time,
                        coreid,
                        "tag6_event",
                        "trigger",
                        event->param1);
                break;
            case TRACE_EVENT_TAG7:
                printf( "%" PRIu64 ",Core_%d,0,STI,%s,0,%s,%" PRIu32 "\n",
                        current_time,
                        coreid,
                        "tag7_event",
                        "trigger",
                        event->param1);
                break;
            default:
                break;
        }
        current_index = ((current_index + 1) % trace_data.h.max_events);
    }
}
#endif

#endif // configUSE_TRACE_FACILITY

