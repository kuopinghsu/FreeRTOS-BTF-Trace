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

#ifndef __FREERTOS_TRACE_H__
#define __FREERTOS_TRACE_H__

#include "btf_trace.h"

#ifndef traceSTART
# define traceSTART() {                         \
    taskENTER_CRITICAL();                       \
    btf_traceSTART();                           \
    taskEXIT_CRITICAL();                        \
}
#endif // traceSTART

#ifndef traceEND
# define traceEND() {                           \
    taskENTER_CRITICAL();                       \
    btf_traceEND();                             \
    taskEXIT_CRITICAL();                        \
}
#endif // traceSTART

#ifndef traceTASK_SWITCHED_IN
# define traceTASK_SWITCHED_IN() {              \
    int mask = taskENTER_CRITICAL_FROM_ISR();   \
    btf_trace_add_event (                       \
        (uint32_t)pxCurrentTCB->uxTCBNumber,    \
        TRACE_EVENT_TASK_SWITCHED_IN            \
    );                                          \
    taskEXIT_CRITICAL_FROM_ISR(mask);           \
}
#endif // traceTASK_SWITCHED_IN

#ifndef traceTASK_SWITCHED_OUT
# define traceTASK_SWITCHED_OUT() {             \
    int mask = taskENTER_CRITICAL_FROM_ISR();   \
    btf_trace_add_event (                       \
        (uint32_t)pxCurrentTCB->uxTCBNumber,    \
        TRACE_EVENT_TASK_SWITCHED_OUT           \
    );                                          \
    taskEXIT_CRITICAL_FROM_ISR(mask);           \
}
#endif // traceTASK_SWITCHED_OUT

#ifndef traceTASK_CREATE
# define traceTASK_CREATE( pxNewTCB ) {         \
    taskENTER_CRITICAL();                       \
    btf_trace_add_task (                        \
        (uint8_t*)pxNewTCB->pcTaskName,         \
        (uint32_t)pxNewTCB->uxTCBNumber,        \
        TRACE_EVENT_TASK_CREATE                 \
    );                                          \
    taskEXIT_CRITICAL();                        \
}
#endif // traceTASK_CREATE

#ifndef traceTASK_DELETE
# define traceTASK_DELETE( pxTCB ) {            \
    taskENTER_CRITICAL();                       \
    btf_trace_add_event (                       \
        (uint32_t)pxTCB->uxTCBNumber,           \
        TRACE_EVENT_TASK_DELETE                 \
    );                                          \
    taskEXIT_CRITICAL();                        \
}
#endif // traceTASK_DELETE

#ifndef traceTASK_SUSPEND
# define traceTASK_SUSPEND( pxTCB ) {           \
    taskENTER_CRITICAL();                       \
    btf_trace_add_event (                       \
        (uint32_t)pxTCB->uxTCBNumber,           \
        TRACE_EVENT_TASK_SUSPEND                \
    );                                          \
    taskEXIT_CRITICAL();                        \
}
#endif // traceTASK_SUSPEND

#ifndef traceTASK_RESUME
# define traceTASK_RESUME( pxTCB ) {            \
    taskENTER_CRITICAL();                       \
    btf_trace_add_event (                       \
        (uint32_t)pxTCB->uxTCBNumber,           \
        TRACE_EVENT_TASK_RESUME                 \
    );                                          \
    taskEXIT_CRITICAL();                        \
}
#endif // traceTASK_RESUME

#ifndef traceTASK_RESUME_FROM_ISR
# define traceTASK_RESUME_FROM_ISR( pxTCB ) {   \
    int mask = taskENTER_CRITICAL_FROM_ISR();   \
    btf_trace_add_event (                       \
        (uint32_t)pxTCB->uxTCBNumber,           \
        TRACE_EVENT_TASK_RESUME_FROM_ISR        \
    );                                          \
    taskEXIT_CRITICAL_FROM_ISR(mask);           \
}
#endif // traceTASK_RESUME_FROM_ISR

#ifndef traceTASK_INCREMENT_TICK
# define traceTASK_INCREMENT_TICK( xTickCount ) {   \
    int mask = taskENTER_CRITICAL_FROM_ISR();   \
    btf_trace_add_event (                       \
        (uint32_t)xTickCount,                   \
        TRACE_EVENT_TASK_INCREMENT_TICK         \
    );                                          \
    taskEXIT_CRITICAL_FROM_ISR(mask);           \
}
#endif // traceTASK_INCREMENT_TICK

#endif // __FREERTOS_TRACE_H__
