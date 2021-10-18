#include <stdio.h>
#include <stdlib.h>
#include "FreeRTOS.h"
#include "task.h"
#include "printf.h"
#include "common.h"

#define NTASKS     8
#define STACK_SIZE 512
#define ITERATIONS 20

volatile int count = 0;

void vTaskTest( void * pvParameters );

/* Task to be created. */
void vMainTask( void * pvParameters )
{
    int i;
    BaseType_t xReturned;

    /* The parameter value is expected to be 1 as 1 is passed in the
    pvParameters value in the call to xTaskCreate() below. */
    configASSERT( ( ( uint32_t ) pvParameters ) == 1 );

    for(i = 0; i < NTASKS; i++) {
        xReturned = xTaskCreate(
                        vTaskTest,       /* Function that implements the task. */
                        "task",          /* Text name for the task. */
                        STACK_SIZE,      /* Stack size in words, not bytes. */
                        ( void * ) 1,    /* Parameter passed into the task. */
                        tskIDLE_PRIORITY,/* Priority at which the task is created. */
                        NULL );      /* Used to pass out the created task's handle. */

        if( xReturned != pdPASS )
        {
            printf("Task create fail\n");
            exit(-1);
        }
    }

    while(count != NTASKS)
        vTaskDelay(2);

#if configUSE_TRACE_FACILITY
    traceEND();
#endif

    exit(0);
}

void vTaskTest( void * pvParameters )
{
    int i;

    /* The parameter value is expected to be 1 as 1 is passed in the
    pvParameters value in the call to xTaskCreate() below. */
    configASSERT( ( ( uint32_t ) pvParameters ) == 1 );

    for(i=0; i<ITERATIONS; i++)
    {
        int j = 0;
        printf("+");
        while(j++ < 1000) asm volatile("" ::: "memory");
        vTaskDelay(rand()%6);
    }

    count++;
    vTaskDelete(NULL);
}

/* Function that creates a task. */
int main( void )
{
    BaseType_t xReturned;
    TaskHandle_t xHandle = NULL;

    printf("Create task\n");

#if configUSE_TRACE_FACILITY
    traceSTART();
#endif

    /* Create the task, storing the handle. */
    xReturned = xTaskCreate(
                    vMainTask,       /* Function that implements the task. */
                    "Main",          /* Text name for the task. */
                    STACK_SIZE,      /* Stack size in words, not bytes. */
                    ( void * ) 1,    /* Parameter passed into the task. */
                    tskIDLE_PRIORITY,/* Priority at which the task is created. */
                    &xHandle );      /* Used to pass out the created task's handle. */

    if( xReturned != pdPASS )
    {
        printf("Task create fail\n");
        exit(-1);
    }

    vTaskStartScheduler();

    /* Should never get here! */
    return 0;
}

