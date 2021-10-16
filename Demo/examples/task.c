#include <stdio.h>
#include <stdlib.h>
#include "FreeRTOS.h"
#include "task.h"
#include "printf.h"
#include "common.h"

#define STACK_SIZE 1024
#define ITERATIONS 50

/* Task to be created. */
void vTaskTest( void * pvParameters )
{
    int i;

    /* The parameter value is expected to be 1 as 1 is passed in the
    pvParameters value in the call to xTaskCreate() below. */
    configASSERT( ( ( uint32_t ) pvParameters ) == 1 );

    for(i=0; i<ITERATIONS; i++)
    {
        vTaskDelay(1);
        printf(".");
    }

    vTaskDelete(NULL);
}

void vTaskTest2( void * pvParameters )
{
    int i;

    /* The parameter value is expected to be 1 as 1 is passed in the
    pvParameters value in the call to xTaskCreate() below. */
    configASSERT( ( ( uint32_t ) pvParameters ) == 1 );

    for(i=0; i<ITERATIONS; i++)
    {
        vTaskDelay(2);
        printf("+");
    }

#if configUSE_TRACE_FACILITY
    traceEND();
#endif

    exit(0);
}

/* Function that creates a task. */
int main( void )
{
    BaseType_t xReturned;
    TaskHandle_t xHandle = NULL;
    TaskHandle_t xHandle2 = NULL;

    printf("Create task\n");

#if configUSE_TRACE_FACILITY
    traceSTART();
#endif

    /* Create the task, storing the handle. */
    xReturned = xTaskCreate(
                    vTaskTest,       /* Function that implements the task. */
                    "Test",          /* Text name for the task. */
                    STACK_SIZE,      /* Stack size in words, not bytes. */
                    ( void * ) 1,    /* Parameter passed into the task. */
                    tskIDLE_PRIORITY,/* Priority at which the task is created. */
                    &xHandle );      /* Used to pass out the created task's handle. */

    if( xReturned != pdPASS )
    {
        printf("Task create fail\n");
        exit(-1);
    }

    xReturned = xTaskCreate(
                    vTaskTest2,      /* Function that implements the task. */
                    "Test",          /* Text name for the task. */
                    STACK_SIZE,      /* Stack size in words, not bytes. */
                    ( void * ) 1,    /* Parameter passed into the task. */
                    tskIDLE_PRIORITY,/* Priority at which the task is created. */
                    &xHandle2 );     /* Used to pass out the created task's handle. */

    if( xReturned != pdPASS )
    {
        printf("Task create fail\n");
        exit(-1);
    }

    vTaskStartScheduler();

    /* Should never get here! */
    return 0;
}

