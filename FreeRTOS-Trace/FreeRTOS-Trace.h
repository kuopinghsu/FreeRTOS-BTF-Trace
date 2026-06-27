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

#ifndef configNUMBER_OF_CORES
#define configNUMBER_OF_CORES 1
#endif

#ifndef configINCLUDE_SCHEDULING
#define configINCLUDE_SCHEDULING 1
#endif

#ifndef configINCLUDE_TAGS
#define configINCLUDE_TAGS 1
#endif

#ifndef configINCLUDE_QUEUE_EVENTS
#define configINCLUDE_QUEUE_EVENTS 1
#endif

#ifndef configINCLUDE_OSTICK_EVENTS
#define configINCLUDE_OSTICK_EVENTS 1
#endif

#define addEVENT( tag, event ) do {                                         \
    taskENTER_CRITICAL();                                                   \
    btf_trace_add_event ( tag, 0, event );                                  \
    taskEXIT_CRITICAL();                                                    \
} while(0)

#define addEVENT_ISR( tag, event ) do {                                     \
    int mask = taskENTER_CRITICAL_FROM_ISR();                               \
    btf_trace_add_event ( tag, 0, event );                                  \
    taskEXIT_CRITICAL_FROM_ISR(mask);                                       \
} while(0)

#ifndef traceSTART
# define traceSTART() do {                                                  \
    taskENTER_CRITICAL();                                                   \
    btf_traceSTART();                                                       \
    taskEXIT_CRITICAL();                                                    \
} while(0)
#endif // traceSTART

#ifndef traceEND
# define traceEND() do {                                                    \
    taskENTER_CRITICAL();                                                   \
    btf_traceEND();                                                         \
    taskEXIT_CRITICAL();                                                    \
} while(0)
#endif // traceEND

#ifndef traceTASK_CREATE
# define traceTASK_CREATE( pxNewTCB ) do {                                  \
    taskENTER_CRITICAL();                                                   \
    btf_trace_add_task (                                                    \
        (uint8_t*)pxNewTCB->pcTaskName,                                     \
        (uint32_t)pxNewTCB->uxTCBNumber,                                    \
        (uint32_t)pxNewTCB->uxPriority,                                     \
        TRACE_EVENT_TASK_CREATE );                                          \
    vTaskSetTaskNumber( (TaskHandle_t)( pxNewTCB ), (pxNewTCB)->uxTCBNumber ); \
    taskEXIT_CRITICAL();                                                    \
} while(0)
#endif // traceTASK_CREATE

#ifndef traceTASK_DELETE
# define traceTASK_DELETE( pxTCB ) addEVENT( (uint32_t)pxTCB->uxTCBNumber, TRACE_EVENT_TASK_DELETE )
#endif // traceTASK_DELETE

#if configINCLUDE_SCHEDULING

#ifndef traceTASK_SWITCHED_IN
# define traceTASK_SWITCHED_IN() addEVENT_ISR( (uint32_t)pxCurrentTCB->uxTCBNumber, TRACE_EVENT_TASK_SWITCHED_IN )
#endif // traceTASK_SWITCHED_IN

#ifndef traceTASK_SWITCHED_OUT
# define traceTASK_SWITCHED_OUT() addEVENT_ISR( (uint32_t)pxCurrentTCB->uxTCBNumber, TRACE_EVENT_TASK_SWITCHED_OUT )
#endif // traceTASK_SWITCHED_OUT

#ifndef traceTASK_SUSPEND
# define traceTASK_SUSPEND( pxTCB ) addEVENT( (uint32_t)pxTCB->uxTCBNumber, TRACE_EVENT_TASK_SUSPEND )
#endif // traceTASK_SUSPEND

#ifndef traceTASK_RESUME
# define traceTASK_RESUME( pxTCB ) addEVENT( (uint32_t)pxTCB->uxTCBNumber, TRACE_EVENT_TASK_RESUME )
#endif // traceTASK_RESUME

#ifndef traceTASK_RESUME_FROM_ISR
# define traceTASK_RESUME_FROM_ISR( pxTCB ) addEVENT_ISR( (uint32_t)pxTCB->uxTCBNumber, TRACE_EVENT_TASK_RESUME_FROM_ISR )
#endif // traceTASK_RESUME_FROM_ISR

#ifndef traceTASK_PRIORITY_SET
# define traceTASK_PRIORITY_SET( pxTCB, uxNewPriority ) do {                \
    taskENTER_CRITICAL();                                                   \
    btf_trace_add_event(                                                    \
        (uint32_t)(pxTCB)->uxTCBNumber,                                     \
        (uint32_t)(uxNewPriority),                                          \
        TRACE_EVENT_TASK_PRIORITY_SET );                                    \
    taskEXIT_CRITICAL();                                                    \
} while(0)
#endif // traceTASK_PRIORITY_SET

#ifndef traceTASK_PRIORITY_INHERIT
# define traceTASK_PRIORITY_INHERIT( pxTCB, uxInheritedPriority ) do {      \
    taskENTER_CRITICAL();                                                   \
    btf_trace_add_event(                                                    \
        (uint32_t)(pxTCB)->uxTCBNumber,                                     \
        (uint32_t)(uxInheritedPriority),                                    \
        TRACE_EVENT_TASK_PRIORITY_INHERIT );                                \
    taskEXIT_CRITICAL();                                                    \
} while(0)
#endif // traceTASK_PRIORITY_INHERIT

#ifndef traceTASK_PRIORITY_DISINHERIT
# define traceTASK_PRIORITY_DISINHERIT( pxTCB, uxOriginalPriority ) do {    \
    taskENTER_CRITICAL();                                                   \
    btf_trace_add_event(                                                    \
        (uint32_t)(pxTCB)->uxTCBNumber,                                     \
        (uint32_t)(uxOriginalPriority),                                     \
        TRACE_EVENT_TASK_PRIORITY_DISINHERIT );                             \
    taskEXIT_CRITICAL();                                                    \
} while(0)
#endif // traceTASK_PRIORITY_DISINHERIT

#endif // configINCLUDE_SCHEDULING

#if configINCLUDE_TAGS

#ifndef traceTAG
# define traceTAG(t,v) do {                                                 \
    taskENTER_CRITICAL();                                                   \
    btf_traceTAG(t, v);                                                     \
    taskEXIT_CRITICAL();                                                    \
} while(0)
#endif // traceTAG

#ifndef traceINTERVAL_START
# define traceINTERVAL_START(id) do {                                       \
    taskENTER_CRITICAL();                                                   \
    btf_traceINTERVAL_START(id);                                            \
    taskEXIT_CRITICAL();                                                    \
} while(0)
#endif // traceINTERVAL_START

#ifndef traceINTERVAL_STOP
# define traceINTERVAL_STOP(id) do {                                        \
    taskENTER_CRITICAL();                                                   \
    btf_traceINTERVAL_STOP(id);                                             \
    taskEXIT_CRITICAL();                                                    \
} while(0)
#endif // traceINTERVAL_STOP

#endif // configINCLUDE_TAGS

#if configINCLUDE_QUEUE_EVENTS

#define addQUEUE_EVENT( pxQueue, event ) do {                               \
    taskENTER_CRITICAL();                                                   \
    btf_trace_add_event(                                                    \
        (uint32_t)(pxQueue)->ucQueueType,                                   \
        (uint32_t)(uintptr_t)(pxQueue),                                     \
        event );                                                            \
    taskEXIT_CRITICAL();                                                    \
} while(0)

#ifndef traceQUEUE_CREATE
# define traceQUEUE_CREATE( pxQueue ) addQUEUE_EVENT( (pxQueue), TRACE_EVENT_QUEUE_CREATE )
#endif // traceQUEUE_CREATE

#ifndef traceQUEUE_SEND
# define traceQUEUE_SEND( pxQueue ) addQUEUE_EVENT( (pxQueue), TRACE_EVENT_QUEUE_SEND )
#endif // traceQUEUE_SEND

#ifndef traceQUEUE_RECEIVE
# define traceQUEUE_RECEIVE( pxQueue ) addQUEUE_EVENT( (pxQueue), TRACE_EVENT_QUEUE_RECEIVE )
#endif // traceQUEUE_RECEIVE

#ifndef traceQUEUE_DELETE
# define traceQUEUE_DELETE( pxQueue ) addQUEUE_EVENT( (pxQueue), TRACE_EVENT_QUEUE_DELETE )
#endif // traceQUEUE_DELETE

#endif // configINCLUDE_QUEUE_EVENTS

#if configINCLUDE_OSTICK_EVENTS

#ifndef traceTASK_INCREMENT_TICK
/* Kernel hook — one STI TICK per invocation (no dedup by tick number). */
# define traceTASK_INCREMENT_TICK( xTickCount ) btf_trace_increment_tick( (uint32_t)( xTickCount ) )
#endif // traceTASK_INCREMENT_TICK

#endif // configINCLUDE_OSTICK_EVENTS

#endif // __FREERTOS_TRACE_H__
