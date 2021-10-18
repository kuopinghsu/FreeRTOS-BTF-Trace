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
    btf_traceTASK_SWITCHED_IN (                 \
        (uint32_t)pxCurrentTCB->uxTCBNumber     \
    );                                          \
    taskEXIT_CRITICAL_FROM_ISR(mask);           \
}
#endif // traceTASK_SWITCHED_IN

#ifndef traceTASK_SWITCHED_OUT
# define traceTASK_SWITCHED_OUT() {             \
    int mask = taskENTER_CRITICAL_FROM_ISR();   \
    btf_traceTASK_SWITCHED_OUT (                \
        (uint32_t)pxCurrentTCB->uxTCBNumber     \
    );                                          \
    taskEXIT_CRITICAL_FROM_ISR(mask);           \
}
#endif // traceTASK_SWITCHED_OUT

#ifndef traceTASK_CREATE
# define traceTASK_CREATE( pxNewTCB ) {         \
    taskENTER_CRITICAL();                       \
    btf_traceTASK_CREATE (                      \
        (uint8_t*)pxNewTCB->pcTaskName,         \
        (uint32_t)pxNewTCB->uxTCBNumber         \
    );                                          \
    taskEXIT_CRITICAL();                        \
}
#endif // traceTASK_CREATE

#ifndef traceTASK_DELETE
# define traceTASK_DELETE( pxTCB ) {            \
    taskENTER_CRITICAL();                       \
    btf_traceTASK_DELETE (                      \
        (uint32_t)pxTCB->uxTCBNumber            \
    );                                          \
    taskEXIT_CRITICAL();                        \
}
#endif // traceTASK_DELETE

#ifndef traceTASK_SUSPEND
# define traceTASK_SUSPEND( pxTCB ) {           \
    taskENTER_CRITICAL();                       \
    btf_traceTASK_SUSPEND (                     \
        (uint32_t)pxTCB->uxTCBNumber            \
    );                                          \
    taskEXIT_CRITICAL();                        \
}
#endif // traceTASK_SUSPEND

#ifndef traceTASK_RESUME
# define traceTASK_RESUME( pxTCB ) {            \
    taskENTER_CRITICAL();                       \
    btf_traceTASK_RESUME (                      \
        (uint32_t)pxTCB->uxTCBNumber            \
    );                                          \
    taskEXIT_CRITICAL();                        \
}
#endif // traceTASK_RESUME

#ifndef traceTASK_RESUME_FROM_ISR
# define traceTASK_RESUME_FROM_ISR( pxTCB ) {   \
    int mask = taskENTER_CRITICAL_FROM_ISR();   \
    btf_traceTASK_RESUME_FROM_ISR (             \
        (uint32_t)pxTCB->uxTCBNumber            \
    );                                          \
    taskEXIT_CRITICAL_FROM_ISR(mask);           \
}
#endif // traceTASK_RESUME_FROM_ISR

#ifndef traceTASK_INCREMENT_TICK
# define traceTASK_INCREMENT_TICK( xTickCount ) {   \
    int mask = taskENTER_CRITICAL_FROM_ISR();   \
    btf_traceTASK_INCREMENT_TICK (              \
        (uint32_t)xTickCount                    \
    );                                          \
    taskEXIT_CRITICAL_FROM_ISR(mask);           \
}
#endif // traceTASK_INCREMENT_TICK

#endif // __FREERTOS_TRACE_H__
