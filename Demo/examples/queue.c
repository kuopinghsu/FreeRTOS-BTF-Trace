#include <stdio.h>
#include <stdlib.h>
#include "FreeRTOS.h"
#include "task.h"
#include "queue.h"
#include "printf.h"
#include "common.h"

#define STACK_SIZE 1024
QueueHandle_t queue;
const int QUEUESIZE = 10000;

/* Task to be created. */
void vTaskProducer( void * pvParameters )
{
    int i;

    /* The parameter value is expected to be 1 as 1 is passed in the
    pvParameters value in the call to xTaskCreate() below. */
    configASSERT( ( ( uint32_t ) pvParameters ) == 1 );

    for(i=0; i<QUEUESIZE; i++){
        xQueueSend(queue, &i, portMAX_DELAY);
        printf(".");
    }

    vTaskDelete( NULL );
}

void vTaskConsumer( void * pvParameters )
{
    int i;
    int element;

    /* The parameter value is expected to be 1 as 1 is passed in the
    pvParameters value in the call to xTaskCreate() below. */
    configASSERT( ( ( uint32_t ) pvParameters ) == 1 );

    for(i=0; i<QUEUESIZE; i++){
        xQueueReceive(queue, &element, portMAX_DELAY);
        printf("+");
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
    TaskHandle_t xHandleP = NULL;
    TaskHandle_t xHandleC = NULL;

#if configUSE_TRACE_FACILITY
    traceSTART();
#endif

    queue = xQueueCreate(QUEUESIZE, sizeof(int));

    if(queue == NULL){
        printf("Can not create queue\n");
        exit(-1);
    }

    printf("Create task\n");

    /* Create the task, storing the handle. */
    xReturned = xTaskCreate(
                    vTaskProducer,   /* Function that implements the task. */
                    "Producer",      /* Text name for the task. */
                    STACK_SIZE,      /* Stack size in words, not bytes. */
                    ( void * ) 1,    /* Parameter passed into the task. */
                    tskIDLE_PRIORITY,/* Priority at which the task is created. */
                    &xHandleP );     /* Used to pass out the created task's handle. */

    if( xReturned != pdPASS )
    {
        printf("Task create fail\n");
        exit(-1);
    }

    xReturned = xTaskCreate(
                    vTaskConsumer,   /* Function that implements the task. */
                    "Consumer",      /* Text name for the task. */
                    STACK_SIZE,      /* Stack size in words, not bytes. */
                    ( void * ) 1,    /* Parameter passed into the task. */
                    tskIDLE_PRIORITY,/* Priority at which the task is created. */
                    &xHandleC );     /* Used to pass out the created task's handle. */

    if( xReturned != pdPASS )
    {
        printf("Task create fail\n");
        exit(-1);
    }

    vTaskStartScheduler();

    /* Should never get here! */
    return 0;
}

