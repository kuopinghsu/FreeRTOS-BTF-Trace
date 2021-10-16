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
