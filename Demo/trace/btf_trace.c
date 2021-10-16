
#include "btf_trace.h"
#include "task.h"
#include <stdio.h>
#include <assert.h>

#if configUSE_TRACE_FACILITY

static uint32_t trace_en;
static TRACE_DATA trace_data;

void btf_traceSTART(void) {
    trace_en = 1;
    trace_data.header[0] = 'B';
    trace_data.header[1] = 'T';
    trace_data.header[2] = 'F';
    trace_data.header[3] = '2';
    trace_data.tag = 1;
    trace_data.max_tasks = configMAX_TASKS;
    trace_data.max_task_name_len = configMAX_TASK_NAME_LEN+6;
    trace_data.max_events = configMAX_EVENTS;
    trace_data.event_count = 0;
}

void btf_traceEND(void) {
    trace_en = 0;
    btf_dump();
}

void btf_traceTASK_SWITCHED_IN (
    uint32_t task_id) {
    if (!trace_en) return;
    assert (trace_data.event_count < configMAX_EVENTS);

    trace_data.event_lists[trace_data.event_count].time = xTaskGetTickCount();
    trace_data.event_lists[trace_data.event_count].param = task_id;
    trace_data.event_lists[trace_data.event_count].types = TRACE_EVENT_TASK_SWITCHED_IN;

    trace_data.event_count++;
}

void btf_traceTASK_SWITCHED_OUT (
    uint32_t task_id) {
    if (!trace_en) return;
    assert (trace_data.event_count < configMAX_EVENTS);

    trace_data.event_lists[trace_data.event_count].time = xTaskGetTickCount();
    trace_data.event_lists[trace_data.event_count].param = task_id;
    trace_data.event_lists[trace_data.event_count].types = TRACE_EVENT_TASK_SWITCHED_OUT;

    trace_data.event_count++;
}

void btf_traceTASK_CREATE (
    uint8_t *task_name,
    uint32_t task_id) {

    char id[6];

    if (!trace_en) return;
    assert (task_id < configMAX_TASKS);
    assert (trace_data.event_count < configMAX_EVENTS);

    sprintf(id, "_%04d", (unsigned)task_id);

    strncpy((char*)trace_data.task_lists[task_id], (char*)task_name, configMAX_TASK_NAME_LEN);
    strncat((char*)trace_data.task_lists[task_id], id, configMAX_TASK_NAME_LEN+5);
    trace_data.max_tasks = task_id;

    trace_data.event_lists[trace_data.event_count].time = xTaskGetTickCount();
    trace_data.event_lists[trace_data.event_count].param = task_id;
    trace_data.event_lists[trace_data.event_count].types = TRACE_EVENT_TASK_CREATE;

    trace_data.event_count++;
}

void btf_traceTASK_SUSPEND (
    uint32_t task_id) {
    if (!trace_en) return;
    assert (trace_data.event_count < configMAX_EVENTS);

    trace_data.event_lists[trace_data.event_count].time = xTaskGetTickCount();
    trace_data.event_lists[trace_data.event_count].param = task_id;
    trace_data.event_lists[trace_data.event_count].types = TRACE_EVENT_TASK_SUSPEND;

    trace_data.event_count++;
}

void btf_traceTASK_RESUME (
    uint32_t task_id) {
    if (!trace_en) return;
    assert (trace_data.event_count < configMAX_EVENTS);

    trace_data.event_lists[trace_data.event_count].time = xTaskGetTickCount();
    trace_data.event_lists[trace_data.event_count].param = task_id;
    trace_data.event_lists[trace_data.event_count].types = TRACE_EVENT_TASK_RESUME;

    trace_data.event_count++;
}

void btf_traceTASK_RESUME_FROM_ISR (
    uint32_t task_id) {
    if (!trace_en) return;
    assert (trace_data.event_count < configMAX_EVENTS);
    trace_data.event_lists[trace_data.event_count].time = xTaskGetTickCount();
    trace_data.event_lists[trace_data.event_count].param = task_id;
    trace_data.event_lists[trace_data.event_count].types = TRACE_EVENT_TASK_RESUME_FROM_ISR;

    trace_data.event_count++;
}

void btf_traceTASK_INCREMENT_TICK (
    uint32_t tick_count) {
    if (!trace_en) return;
    assert (trace_data.event_count < configMAX_EVENTS);

    trace_data.event_lists[trace_data.event_count].time = xTaskGetTickCount();
    trace_data.event_lists[trace_data.event_count].param = tick_count;
    trace_data.event_lists[trace_data.event_count].types = TRACE_EVENT_TASK_INCREMENT_TICK;

    trace_data.event_count++;
}

void btf_dump(
    void) {
    int i;

    printf("\n");
    printf("#version 2.2.0\n");
    printf("#creator FreeRTOS trace logger\n");
    printf("#createDate " __DATE__ " " __TIME__ "\n");
    printf("#timeScale ns\n");

    for(i=0; i<trace_data.event_count; i++) {
        switch(trace_data.event_lists[i].types) {
            case TRACE_EVENT_TASK_SWITCHED_IN:
                 printf("%ld, %s, %d, task_switched_in\n",
                         trace_data.event_lists[i].time,
                         trace_data.task_lists[trace_data.event_lists[i].param],
                         trace_data.event_lists[i].types);
                 break;
            case TRACE_EVENT_TASK_SWITCHED_OUT:
                 printf("%ld, %s, %d, task_swithed_out\n",
                         trace_data.event_lists[i].time,
                         trace_data.task_lists[trace_data.event_lists[i].param],
                         trace_data.event_lists[i].types);
                 break;
            case TRACE_EVENT_TASK_CREATE:
                 printf("%ld, %s, %d, task_create\n",
                         trace_data.event_lists[i].time,
                         trace_data.task_lists[trace_data.event_lists[i].param],
                         trace_data.event_lists[i].types);
                 break;
            case TRACE_EVENT_TASK_SUSPEND:
                 printf("%ld, %s, %d, task_suspend\n",
                         trace_data.event_lists[i].time,
                         trace_data.task_lists[trace_data.event_lists[i].param],
                         trace_data.event_lists[i].types);
                 break;
            case TRACE_EVENT_TASK_RESUME:
                 printf("%ld, %s, %d, task_resume\n",
                         trace_data.event_lists[i].time,
                         trace_data.task_lists[trace_data.event_lists[i].param],
                         trace_data.event_lists[i].types);
                 break;
            case TRACE_EVENT_TASK_RESUME_FROM_ISR:
                 printf("%ld, %s, %d, resume_from_isr\n",
                         trace_data.event_lists[i].time,
                         trace_data.task_lists[trace_data.event_lists[i].param],
                         trace_data.event_lists[i].types);
                break;
            case TRACE_EVENT_TASK_INCREMENT_TICK:
                 printf("%ld, %ld, %d, increment_tick\n",
                         trace_data.event_lists[i].time,
                         trace_data.event_lists[i].param,
                         trace_data.event_lists[i].types);
                break;
            default:
                break;
        }
    }
}

#endif // configUSE_TRACE_FACILITY

