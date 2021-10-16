#include <stdio.h>
#include <stdlib.h>
#include "FreeRTOS.h"
#include "task.h"
#include "queue.h"
#include "semphr.h"
#include "printf.h"
#include "common.h"

#define STACK_SIZE 1024
#define ITERATIONS 100
SemaphoreHandle_t xSemaphore;

/* Task to be created. */
void vTask1( void * pvParameters )
{
    int i;

    /* The parameter value is expected to be 1 as 1 is passed in the
    pvParameters value in the call to xTaskCreate() below. */
    configASSERT( ( ( uint32_t ) pvParameters ) == 1 );

    for(i=0; i<ITERATIONS; i++) {
        xSemaphoreGive( xSemaphore );
        printf(".");
        taskYIELD();
    }

    vTaskDelete( NULL );
}

void vTask2( void * pvParameters )
{
    int i;

    /* The parameter value is expected to be 1 as 1 is passed in the
    pvParameters value in the call to xTaskCreate() below. */
    configASSERT( ( ( uint32_t ) pvParameters ) == 1 );

    for(i=0; i<ITERATIONS; i++) {
        if( xSemaphoreTake( xSemaphore, 10 /* portMAX_DELAY */) == pdTRUE ) {
            printf("+");
        }
    }

#if configUSE_TRACE_FACILITY
    traceEND();
#endif

    printf("\nDone\n");
    exit(0);
}

/* Function that creates a task. */
int main( void )
{
    BaseType_t xReturned;
    TaskHandle_t xHandle1 = NULL;
    TaskHandle_t xHandle2 = NULL;

#if configUSE_TRACE_FACILITY
    traceSTART();
#endif

    xSemaphore = xSemaphoreCreateMutex();

    if( xSemaphore == NULL )
    {
        printf("Can not create mutex\n");
        exit(-1);
    }

    printf("Create task\n");

    /* Create the task, storing the handle. */
    xReturned = xTaskCreate(
                    vTask1,          /* Function that implements the task. */
                    "Task1",         /* Text name for the task. */
                    STACK_SIZE,      /* Stack size in words, not bytes. */
                    ( void * ) 1,    /* Parameter passed into the task. */
                    tskIDLE_PRIORITY,/* Priority at which the task is created. */
                    &xHandle1 );     /* Used to pass out the created task's handle. */

    if( xReturned != pdPASS )
    {
        printf("Task create fail\n");
        exit(-1);
    }

    xReturned = xTaskCreate(
                    vTask2,          /* Function that implements the task. */
                    "Task2",         /* Text name for the task. */
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

