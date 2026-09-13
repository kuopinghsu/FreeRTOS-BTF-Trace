/* 128-core FreeRTOS SMP synchronization stress test.
 *
 * Creates one affinity-pinned worker per core. Work is distributed through
 * per-worker queues; workers contend on ordered mutex pairs and a counting
 * semaphore, report through a result queue, and signal cohort event groups.
 */
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>

#include "FreeRTOS.h"
#include "event_groups.h"
#include "queue.h"
#include "semphr.h"
#include "task.h"

#if ( configNUMBER_OF_CORES != 128 )
    #error "stress_128 must be built with CORES=128"
#endif

#define WORKER_COUNT       128U
#define SHARD_COUNT        128U
#define COHORT_SIZE         16U
#define COHORT_COUNT         8U
#define MUTEX_COUNT          8U
#define ROUNDS               4U
#define WORK_QUEUE_DEPTH     4U
#define RESULT_QUEUE_DEPTH 128U
#define WORKER_STACK_WORDS 256U

typedef struct
{
    uint32_t sequence;
    uint32_t target;
    uint32_t payload;
} WorkItem_t;

typedef struct
{
    uint32_t sequence;
    uint32_t worker;
    uint32_t core;
    uint32_t value;
} Result_t;

static QueueHandle_t xWorkQueues[ SHARD_COUNT ];
static QueueHandle_t xResultQueue;
static SemaphoreHandle_t xResourceSlots;
static SemaphoreHandle_t xLedgerMutexes[ MUTEX_COUNT ];
static EventGroupHandle_t xRoundEvents[ COHORT_COUNT ];
static uint32_t ulLedger[ MUTEX_COUNT ];
static volatile uint32_t ulFailures;

extern void freertos_risc_v_trap_handler( void );

void vApplicationTickHook( void ) {}

void vApplicationStackOverflowHook( TaskHandle_t xTask, char * pcTaskName )
{
    ( void ) xTask;
    printf( "stack overflow: %s\n", pcTaskName );
    exit( 2 );
}

static uint32_t prvMix( uint32_t x )
{
    x ^= x >> 16;
    x *= UINT32_C( 0x7feb352d );
    x ^= x >> 15;
    x *= UINT32_C( 0x846ca68b );
    return x ^ ( x >> 16 );
}

static void prvWorker( void * pvArg )
{
    const uint32_t worker = ( uint32_t ) ( uintptr_t ) pvArg;
    const uint32_t cohort = worker / COHORT_SIZE;
    const EventBits_t doneBit = ( EventBits_t ) 1U << ( worker % COHORT_SIZE );
    WorkItem_t item;

    configASSERT( portGET_CORE_ID() == worker );

    for( ; ; )
    {
        uint32_t first;
        uint32_t second;
        uint32_t value;
        Result_t result;

        configASSERT( xQueueReceive( xWorkQueues[ worker ],
                                    &item, portMAX_DELAY ) == pdPASS );
        if( item.target != worker )
        {
            ulFailures++;
        }

        configASSERT( xSemaphoreTake( xResourceSlots, portMAX_DELAY ) == pdPASS );

        first = item.sequence % MUTEX_COUNT;
        second = ( item.sequence * 5U + worker + 1U ) % MUTEX_COUNT;
        if( first == second )
        {
            second = ( second + 1U ) % MUTEX_COUNT;
        }
        if( first > second )
        {
            const uint32_t swap = first;
            first = second;
            second = swap;
        }

        configASSERT( xSemaphoreTake( xLedgerMutexes[ first ],
                                      portMAX_DELAY ) == pdPASS );
        configASSERT( xSemaphoreTake( xLedgerMutexes[ second ],
                                      portMAX_DELAY ) == pdPASS );
        value = prvMix( item.payload ^ worker ^ item.sequence );
        ulLedger[ first ] ^= value;
        ulLedger[ second ] += value;
        xSemaphoreGive( xLedgerMutexes[ second ] );
        xSemaphoreGive( xLedgerMutexes[ first ] );
        xSemaphoreGive( xResourceSlots );

        result.sequence = item.sequence;
        result.worker = worker;
        result.core = ( uint32_t ) portGET_CORE_ID();
        result.value = value;
        configASSERT( xQueueSend( xResultQueue, &result, portMAX_DELAY ) == pdPASS );
        xEventGroupSetBits( xRoundEvents[ cohort ], doneBit );
    }
}

static void prvController( void * pvArg )
{
    uint32_t round;
    ( void ) pvArg;

    for( round = 0; round < ROUNDS; round++ )
    {
        uint32_t i;

        for( i = 0; i < COHORT_COUNT; i++ )
        {
            xEventGroupClearBits( xRoundEvents[ i ], UINT16_MAX );
        }

        for( i = 0; i < WORKER_COUNT; i++ )
        {
            WorkItem_t item;
            item.sequence = round * WORKER_COUNT + i;
            item.target = i;
            item.payload = UINT32_C( 0x12340000 ) ^ ( round << 8 ) ^ i;
            configASSERT( xQueueSend( xWorkQueues[ i ],
                                      &item, portMAX_DELAY ) == pdPASS );
        }

        for( i = 0; i < COHORT_COUNT; i++ )
        {
            const EventBits_t bits = xEventGroupWaitBits(
                xRoundEvents[ i ], UINT16_MAX, pdFALSE, pdTRUE, portMAX_DELAY );
            if( ( bits & UINT16_MAX ) != UINT16_MAX )
            {
                ulFailures++;
            }
        }

        for( i = 0; i < WORKER_COUNT; i++ )
        {
            Result_t result;
            configASSERT( xQueueReceive( xResultQueue, &result,
                                         portMAX_DELAY ) == pdPASS );
            if( ( result.worker >= WORKER_COUNT ) ||
                ( result.core != result.worker ) ||
                ( result.sequence / WORKER_COUNT != round ) )
            {
                ulFailures++;
            }
        }

        printf( "stress128 round %u/%u: %s\n", ( unsigned ) round + 1U,
                ( unsigned ) ROUNDS,
                ( ulFailures == 0U ) ? "PASS" : "FAIL" );
    }

    printf( "stress128 complete: failures=%u ledger=%08x/%08x\n",
            ( unsigned ) ulFailures, ( unsigned ) ulLedger[ 0 ],
            ( unsigned ) ulLedger[ MUTEX_COUNT - 1U ] );
    configASSERT( ulFailures == 0U );
    #if ( configUSE_TRACE_FACILITY == 1 )
        traceEND();
    #endif
    exit( 0 );
}

int main( void )
{
    uint32_t i;

    __asm__ volatile( "csrw mtvec, %0" : : "r"( ( uintptr_t ) freertos_risc_v_trap_handler ) : "memory" );
    #if ( configUSE_TRACE_FACILITY == 1 )
        traceSTART();
    #endif

    for( i = 0; i < SHARD_COUNT; i++ )
    {
        xWorkQueues[ i ] = xQueueCreate( WORK_QUEUE_DEPTH, sizeof( WorkItem_t ) );
        configASSERT( xWorkQueues[ i ] != NULL );
    }
    xResultQueue = xQueueCreate( RESULT_QUEUE_DEPTH, sizeof( Result_t ) );
    xResourceSlots = xSemaphoreCreateCounting( 32U, 32U );
    configASSERT( ( xResultQueue != NULL ) && ( xResourceSlots != NULL ) );

    for( i = 0; i < MUTEX_COUNT; i++ )
    {
        xLedgerMutexes[ i ] = xSemaphoreCreateMutex();
        configASSERT( xLedgerMutexes[ i ] != NULL );
    }
    for( i = 0; i < COHORT_COUNT; i++ )
    {
        xRoundEvents[ i ] = xEventGroupCreate();
        configASSERT( xRoundEvents[ i ] != NULL );
    }

    for( i = 0; i < WORKER_COUNT; i++ )
    {
        char name[ configMAX_TASK_NAME_LEN ];
        ( void ) snprintf( name, sizeof( name ), "W%03u", ( unsigned ) i );
        configASSERT( xTaskCreateAffinitySet(
            prvWorker, name, WORKER_STACK_WORDS, ( void * ) ( uintptr_t ) i,
            tskIDLE_PRIORITY + 2U, taskCORE_AFFINITY_BIT( i ), NULL ) == pdPASS );
    }
    configASSERT( xTaskCreateAffinitySet(
        prvController, "CTRL", WORKER_STACK_WORDS, NULL,
        tskIDLE_PRIORITY + 3U, taskCORE_AFFINITY_BIT( 0 ), NULL ) == pdPASS );

    vTaskStartScheduler();
    configASSERT( 0 );
    return 1;
}
