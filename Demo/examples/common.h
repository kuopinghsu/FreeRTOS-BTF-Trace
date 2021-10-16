#ifndef __COMMON_H

#include <stdlib.h>
#include "task.h"

#if configUSE_MALLOC_FAILED_HOOK
void vApplicationMallocFailedHook ( void )
{
    printf("\nMalloc fail, stopping.");
    exit(0);
}
#endif

#if configCHECK_FOR_STACK_OVERFLOW
void vApplicationStackOverflowHook( TaskHandle_t xTask, char *pcTaskName )
{
    printf("\n%s: Stack overflow, stopping.", pcTaskName);
    exit(0);
}
#endif

#if configUSE_TICK_HOOK && !defined(USER_DEFINED_TICK_HOOK)
void vApplicationTickHook( void )
{
    /* empty */
}
#endif

#if configUSE_IDLE_HOOK && !defined(USER_DEFINED_IDLE_HOOK)
void vApplicationIdleHook( void )
{
    /* empty */
}
#endif

#endif // __COMMON_H
