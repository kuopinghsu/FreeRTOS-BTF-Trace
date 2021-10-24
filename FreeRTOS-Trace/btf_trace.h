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

#ifndef __BTF_TRACE_H__
#define __BTF_TRACE_H__

#include <stdint.h>
#include <string.h>

#define TRACE_VER_MAJOR     1
#define TRACE_VER_MINOR     2
#define TRACE_VERSION       ((TRACE_VER_MAJOR<<16)|TRACE_VER_MINOR)

#define configMAX_TASKS     1024
#define configMAX_EVENTS    4096

#ifndef configMAX_TASK_NAME_LEN
#define configMAX_TASK_NAME_LEN 8
#endif

#define ALIGN4(n) (((n)+3)&0xfffffffc)

typedef enum {
    TRACE_EVENT_TASK_SWITCHED_IN     = 1,
    TRACE_EVENT_TASK_SWITCHED_OUT    = 2,
    TRACE_EVENT_TASK_CREATE          = 3,
    TRACE_EVENT_TASK_DELETE          = 4,
    TRACE_EVENT_TASK_SUSPEND         = 5,
    TRACE_EVENT_TASK_RESUME          = 6,
    TRACE_EVENT_TASK_RESUME_FROM_ISR = 7,
    TRACE_EVENT_TASK_INCREMENT_TICK  = 8
} event_t;

typedef struct {
    uint32_t    time;
    uint32_t    value;
    event_t     types;
} EVENT;

typedef struct {
    char        header[4];
    uint32_t    tag;
    uint32_t    version;
    uint32_t    core_clock;
    uint32_t    max_tasks;
    uint32_t    max_taskname_len;
    uint32_t    max_events;
    uint32_t    task_count;
    uint32_t    event_count;
    uint32_t    current_index;
} TRACE_HEADER;

typedef struct {
    uint8_t     task_lists[configMAX_TASKS][ALIGN4(configMAX_TASK_NAME_LEN+1)];
    EVENT       event_lists[configMAX_EVENTS];
} TRACE_DATA;

typedef struct {
    TRACE_HEADER h;
    TRACE_DATA   d;
} TRACE;

void btf_traceSTART(void);
void btf_traceEND(void);
void btf_trace_add_task(uint8_t *task_name, uint32_t task_id, event_t event);
void btf_trace_add_event(uint32_t value, event_t event);
void btf_dump(void);

#endif // __BTF_TRACE_H__

