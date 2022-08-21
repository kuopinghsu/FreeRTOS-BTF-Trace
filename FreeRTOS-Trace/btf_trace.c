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
#include <assert.h>
#include "FreeRTOS.h"
#include "btf_trace.h"
#include "task.h"

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

#define BUILD_DAY   ((((__DATE__[4] >= '0') ? (__DATE__[4]) : '0') - '0') * 10 + (__DATE__[ 5]) - '0')

// Example of __TIME__ string: "21:06:19"
//                              01234567
#define BUILD_HOUR ((__TIME__[0] - '0') * 10 + (__TIME__[1] - '0'))
#define BUILD_MIN  ((__TIME__[3] - '0') * 10 + (__TIME__[4] - '0'))
#define BUILD_SEC  ((__TIME__[6] - '0') * 10 + (__TIME__[7] - '0'))

#if configUSE_TRACE_FACILITY

#include "btf_port.h"

static uint32_t trace_en;
static TRACE trace_data;

void btf_traceSTART(void) {
    trace_en = 1;
    trace_data.h.header[0] = 'B';
    trace_data.h.header[1] = 'T';
    trace_data.h.header[2] = 'F';
    trace_data.h.header[3] = '2';
    trace_data.h.tag = 1;
    trace_data.h.version = TRACE_VERSION;
    trace_data.h.core_clock = configCPU_CLOCK_HZ;
    trace_data.h.max_tasks = configMAX_TRACE_TASKS;
    trace_data.h.max_taskname_len = ALIGN4(configMAX_TRACE_TASK_NAME_LEN+1);
    trace_data.h.max_events = configMAX_TRACE_EVENTS;
    trace_data.h.task_count = 0;
    trace_data.h.event_count = 0;
    trace_data.h.current_index = 0;
}

void btf_traceEND(void) {
    trace_en = 0;

#ifdef HAVE_SYS_DUMP
    sys_dump((int)&trace_data, (int)sizeof(trace_data));
#endif
#ifdef PRINT_BTF_DUMP
    btf_dump();
#endif

    printf("%ld events generated.\n", trace_data.h.event_count);
}

void btf_trace_add_task (
    uint8_t *task_name,
    uint32_t task_id,
    event_t  event)
{
    if (!trace_en) return;
    assert (trace_data.h.event_count <= configMAX_TRACE_EVENTS);

    if (task_id > configMAX_TRACE_TASKS) {
        printf("Warning: the maximum number of tasks allowed is exceeded and cannot be tracked.\n");
        trace_en = 0;
        return;
    }

    // task_id is a unique ID, which will increase by 1 each time a TCB is created.
    strncpy((char*)trace_data.d.task_lists[task_id], (char*)task_name, configMAX_TRACE_TASK_NAME_LEN);
    trace_data.d.task_lists[task_id][configMAX_TRACE_TASK_NAME_LEN] = 0;
    trace_data.h.task_count++;

    trace_data.d.event_lists[trace_data.h.current_index].time = xGetTime();
    trace_data.d.event_lists[trace_data.h.current_index].value = task_id;
    trace_data.d.event_lists[trace_data.h.current_index].types = event;

    trace_data.h.current_index++;
    if (trace_data.h.current_index == configMAX_TRACE_EVENTS) {
        trace_data.h.current_index = 0;
        printf("\nWarning: trace data wrap, only last events will be recorded.\n");
    }
    if (trace_data.h.event_count < configMAX_TRACE_EVENTS)
        trace_data.h.event_count++;
}

void btf_trace_add_event (
    uint32_t value,
    event_t  event)
{
    if (!trace_en) return;
    assert (trace_data.h.event_count <= configMAX_TRACE_EVENTS);
    assert (trace_data.h.current_index < configMAX_TRACE_EVENTS);

    trace_data.d.event_lists[trace_data.h.current_index].time = xGetTime();
    trace_data.d.event_lists[trace_data.h.current_index].value = value;
    trace_data.d.event_lists[trace_data.h.current_index].types = event;

    trace_data.h.current_index++;
    if (trace_data.h.current_index == configMAX_TRACE_EVENTS) {
        trace_data.h.current_index = 0;
        printf("\nWarning: trace data wrap, only last events will be recorded.\n");
    }
    if (trace_data.h.event_count < configMAX_TRACE_EVENTS)
        trace_data.h.event_count++;
}

#ifdef PRINT_BTF_DUMP
#define get_taskname(n,i) n.d.task_lists[i]
#define get_event(n,i) (&n.d.event_lists[i])
void btf_dump(
    void) {
    int i;
    int current_task;
    int current_index;
    EVENT *event;

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
    // YYYY-MMDDTHH:MM:SS. The time should be in UTC time (indicated by a “Z” at the
    // end)
    printf("#creationDate %04d-%02d-%02dT%02d:%02d:%02dZ\n", BUILD_YEAR, BUILD_MONTH,
           BUILD_DAY, BUILD_HOUR, BUILD_MIN, BUILD_SEC);

    printf("#timeScale ns\n");

    if (trace_data.h.event_count != trace_data.h.max_events)
        current_index = 0;
    else
        current_index = trace_data.h.current_index;

    event = get_event(trace_data, current_index);

    printf("%u,Core_1,0,C,Core_1,0,set_frequency,%ld\n",
           event->list, trace_data.h.core_clock);

    current_task = 0;

    for(i = 0; i < trace_data.h.event_count; i++) {
        event = get_event(trace_data, current_index);

        switch(event->types) {
            case TRACE_EVENT_TASK_SWITCHED_IN:
                printf( "%u,(%04d)%s,0,T,(%04d)%s,0,%s,%s\n",
                        event->time,
                        current_task, get_taskname(trace_data, current_task),
                        event->value, get_taskname(trace_data, event->value),
                        "resume",
                        "");
                break;
            case TRACE_EVENT_TASK_SWITCHED_OUT:
                printf( "%u,(%04d)%s,0,T,(%04d)%s,0,%s,%s\n",
                        event->time,
                        current_task, get_taskname(trace_data, current_task),
                        event->value, get_taskname(trace_data, event->value),
                        "preempt",
                        "");
                break;
            case TRACE_EVENT_TASK_CREATE:
                printf( "%u,%s,0,T,(%04d)%s,0,%s,%s\n",
                        event->time,
                        "Core_1",
                        event->value, get_taskname(trace_data, event->value),
                        "preempt",
                        "create");
                break;
            case TRACE_EVENT_TASK_DELETE:
                // FIXME
                printf( "%u,%s,0,R,(%04d)%s,0,%s,%s\n",
                        event->time,
                        "Core_1",
                        event->value, get_taskname(trace_data, event->value),
                        "preempt",
                        "delete");
                break;
            case TRACE_EVENT_TASK_SUSPEND:
                printf( "%u,(%04d)%s,0,T,(%04d)%s,0,%s,%s\n",
                        event->time,
                        current_task, get_taskname(trace_data, current_task),
                        event->value, get_taskname(trace_data, event->value),
                        "wait",
                        "suspend");
                break;
            case TRACE_EVENT_TASK_RESUME:
                printf( "%u,(%04d)%s,0,T,(%04d)%s,0,%s,%s\n",
                        event->time,
                        current_task, get_taskname(trace_data, current_task),
                        event->value, get_taskname(trace_data, event->value),
                        "release",
                        "resume");
                break;
            case TRACE_EVENT_TASK_RESUME_FROM_ISR:
                printf( "%u,%s,0,T,(%04d)%s,0,%s,%s\n",
                        event->time,
                        "Core_1",
                        event->value, get_taskname(trace_data, event->value),
                        "release",
                        "resume/isr");
                break;
            case TRACE_EVENT_TASK_INCREMENT_TICK:
                // FIXME
                printf( "%u,%s,0,STI,%s,0,%s,tick_%ld\n",
                        event->time,
                        "Core_1",
                        "tick_event",
                        "trigger",
                        event->value);
                break;
            default:
                break;
        }
        current_task = event->value;
        current_index = ((current_index + 1) % trace_data.h.max_events);
    }
}
#endif

#endif // configUSE_TRACE_FACILITY

