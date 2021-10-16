#ifndef __BTF_TRACE_H__
#define __BTF_TRACE_H__

#define configMAX_TASKS     1024
#define configMAX_EVENTS    4096

#include "FreeRTOS.h"
#include <stdint.h>
#include <string.h>

typedef enum {
    TRACE_EVENT_TASK_SWITCHED_IN     = 1,
    TRACE_EVENT_TASK_SWITCHED_OUT    = 2,
    TRACE_EVENT_TASK_CREATE          = 3,
    TRACE_EVENT_TASK_SUSPEND         = 4,
    TRACE_EVENT_TASK_RESUME          = 5,
    TRACE_EVENT_TASK_RESUME_FROM_ISR = 6,
    TRACE_EVENT_TASK_INCREMENT_TICK  = 7
} event_t;

typedef struct {
    uint32_t    time;
    uint32_t    param;
    event_t     types;
} EVENT;

typedef struct {
    char        header[4];
    uint32_t    tag;
    uint32_t    max_tasks;
    uint32_t    max_task_name_len;
    uint32_t    max_events;
    uint8_t     task_lists[configMAX_TASKS][configMAX_TASK_NAME_LEN+6];
    uint32_t    event_count;
    EVENT       event_lists[configMAX_EVENTS];
} TRACE_DATA;

void btf_traceSTART(void);

void btf_traceEND(void);

void btf_traceTASK_SWITCHED_IN (
    uint32_t task_id);

void btf_traceTASK_SWITCHED_OUT (
    uint32_t task_id);

void btf_traceTASK_CREATE (
    uint8_t *task_name,
    uint32_t task_id);

void btf_traceTASK_SUSPEND (
    uint32_t task_id);

void btf_traceTASK_RESUME (
    uint32_t task_id);

void btf_traceTASK_RESUME_FROM_ISR (
    uint32_t task_id);

void btf_traceTASK_INCREMENT_TICK (
    uint32_t tick_count);

void btf_dump(
    void);

#endif // __BTF_TRACE_H__

