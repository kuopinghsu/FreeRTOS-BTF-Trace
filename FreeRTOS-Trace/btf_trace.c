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
        printf("Warnning: the maximum number of tasks allowed is exceeded and cannot be tracked.\n");
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
        printf("\nWarnning: trace data wrap, only last events will be recorded.\n");
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
        printf("\nWarnning: trace data wrap, only last events will be recorded.\n");
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
    printf("#createDate " __DATE__ " " __TIME__ "\n");
    printf("#timeScale ns\n");

    current_task = 0;
    if (trace_data.h.event_count != trace_data.h.max_events) {
        current_index = 0;
    } else {
        current_index = trace_data.h.current_index == 0 ?
                        trace_data.h.max_events - 1 :
                        trace_data.h.current_index;
    }

    event = get_event(trace_data, current_index);

    printf("%u,Core_1,0,C,Core_1,0,set_frequence,%ld\n",
           event->list, trace_data.h.core_clock);


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

