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
#define WORKER_STACK_WORDS     384U
#define CONTROLLER_STACK_WORDS 1024U
#define COHORT_TIMEOUT_TICKS pdMS_TO_TICKS( 2000U )

#define STRESS_PROGRESS( ... ) do { printf( __VA_ARGS__ ); fflush( stdout ); } while( 0 )

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
static volatile uint8_t ucWorkerStage[ WORKER_COUNT ];

extern void freertos_risc_v_trap_handler( void );

void vApplicationTickHook( void ) {}

void vApplicationStackOverflowHook( TaskHandle_t xTask, char * pcTaskName )
{
    ( void ) xTask;
    printf( "stack overflow: %s\n", pcTaskName );
    fflush( stdout );
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
        ucWorkerStage[ worker ] = 1U;
        if( item.target != worker )
        {
            ulFailures++;
        }

        configASSERT( xSemaphoreTake( xResourceSlots, portMAX_DELAY ) == pdPASS );
        ucWorkerStage[ worker ] = 2U;

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
        ucWorkerStage[ worker ] = 3U;

        result.sequence = item.sequence;
        result.worker = worker;
        result.core = ( uint32_t ) portGET_CORE_ID();
        result.value = value;
        configASSERT( xQueueSend( xResultQueue, &result, portMAX_DELAY ) == pdPASS );
        ucWorkerStage[ worker ] = 4U;
        xEventGroupSetBits( xRoundEvents[ cohort ], doneBit );
        ucWorkerStage[ worker ] = 5U;
    }
}

static void prvController( void * pvArg )
{
    uint32_t round;
    ( void ) pvArg;

    for( round = 0; round < ROUNDS; round++ )
    {
        uint32_t i;

        STRESS_PROGRESS( "[stress128] round %u/%u: clearing barriers\n",
                         ( unsigned ) round + 1U, ( unsigned ) ROUNDS );

        for( i = 0; i < COHORT_COUNT; i++ )
        {
            xEventGroupClearBits( xRoundEvents[ i ], UINT16_MAX );
        }

        for( i = 0; i < WORKER_COUNT; i++ )
        {
            WorkItem_t item;
            ucWorkerStage[ i ] = 0U;
            item.sequence = round * WORKER_COUNT + i;
            item.target = i;
            item.payload = UINT32_C( 0x12340000 ) ^ ( round << 8 ) ^ i;
            configASSERT( xQueueSend( xWorkQueues[ i ],
                                      &item, portMAX_DELAY ) == pdPASS );
        }

        STRESS_PROGRESS( "[stress128] round %u/%u: queued %u jobs; waiting for cohorts\n",
                         ( unsigned ) round + 1U, ( unsigned ) ROUNDS,
                         ( unsigned ) WORKER_COUNT );

        for( i = 0; i < COHORT_COUNT; i++ )
        {
            const EventBits_t bits = xEventGroupWaitBits(
                xRoundEvents[ i ], UINT16_MAX, pdFALSE, pdTRUE,
                COHORT_TIMEOUT_TICKS );
            if( ( bits & UINT16_MAX ) != UINT16_MAX )
            {
                uint32_t worker;
                uint32_t stageCounts[ 6 ] = { 0U };

                for( worker = 0; worker < WORKER_COUNT; worker++ )
                {
                    const uint8_t stage = ucWorkerStage[ worker ];
                    if( stage <= 5U )
                    {
                        stageCounts[ stage ]++;
                    }
                }
                STRESS_PROGRESS( "[stress128] TIMEOUT cohort %u: bits=%04x missing=%04x stages=%u/%u/%u/%u/%u/%u\n",
                                 ( unsigned ) i + 1U,
                                 ( unsigned ) ( bits & UINT16_MAX ),
                                 ( unsigned ) ( UINT16_MAX & ~bits ),
                                 ( unsigned ) stageCounts[ 0 ],
                                 ( unsigned ) stageCounts[ 1 ],
                                 ( unsigned ) stageCounts[ 2 ],
                                 ( unsigned ) stageCounts[ 3 ],
                                 ( unsigned ) stageCounts[ 4 ],
                                 ( unsigned ) stageCounts[ 5 ] );
                exit( 3 );
            }
            STRESS_PROGRESS( "[stress128] round %u/%u: cohort %u/%u complete\n",
                             ( unsigned ) round + 1U, ( unsigned ) ROUNDS,
                             ( unsigned ) i + 1U, ( unsigned ) COHORT_COUNT );
        }

        STRESS_PROGRESS( "[stress128] round %u/%u: validating %u results\n",
                         ( unsigned ) round + 1U, ( unsigned ) ROUNDS,
                         ( unsigned ) WORKER_COUNT );

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

        STRESS_PROGRESS( "[stress128] round %u/%u: %s (failures=%u, CTRL stack low-water=%u words)\n",
                         ( unsigned ) round + 1U, ( unsigned ) ROUNDS,
                         ( ulFailures == 0U ) ? "PASS" : "FAIL",
                         ( unsigned ) ulFailures,
                         ( unsigned ) uxTaskGetStackHighWaterMark( NULL ) );
    }

    STRESS_PROGRESS( "[stress128] complete: failures=%u ledger=%08x/%08x\n",
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

    ( void ) setvbuf( stdout, NULL, _IONBF, 0 );
    STRESS_PROGRESS( "[stress128] boot: 128 cores, %u rounds\n",
                     ( unsigned ) ROUNDS );

    __asm__ volatile( "csrw mtvec, %0" : : "r"( ( uintptr_t ) freertos_risc_v_trap_handler ) : "memory" );
    #if ( configUSE_TRACE_FACILITY == 1 )
        traceSTART();
    #endif

    for( i = 0; i < SHARD_COUNT; i++ )
    {
        xWorkQueues[ i ] = xQueueCreate( WORK_QUEUE_DEPTH, sizeof( WorkItem_t ) );
        configASSERT( xWorkQueues[ i ] != NULL );
    }
    STRESS_PROGRESS( "[stress128] created 128 worker queues\n" );
    xResultQueue = xQueueCreate( RESULT_QUEUE_DEPTH, sizeof( Result_t ) );
    xResourceSlots = xSemaphoreCreateCounting( 32U, 32U );
    configASSERT( ( xResultQueue != NULL ) && ( xResourceSlots != NULL ) );
    STRESS_PROGRESS( "[stress128] created result queue and 32-slot semaphore\n" );

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
    STRESS_PROGRESS( "[stress128] created 8 mutexes and 8 event groups\n" );

    for( i = 0; i < WORKER_COUNT; i++ )
    {
        char name[ configMAX_TASK_NAME_LEN ];
        ( void ) snprintf( name, sizeof( name ), "W%03u", ( unsigned ) i );
        configASSERT( xTaskCreateAffinitySet(
            prvWorker, name, WORKER_STACK_WORDS, ( void * ) ( uintptr_t ) i,
            tskIDLE_PRIORITY + 2U, taskCORE_AFFINITY_BIT( i ), NULL ) == pdPASS );
        if( ( ( i + 1U ) % 16U ) == 0U )
        {
            STRESS_PROGRESS( "[stress128] workers created: %u/128\n",
                             ( unsigned ) i + 1U );
        }
    }
    configASSERT( xTaskCreateAffinitySet(
        prvController, "CTRL", CONTROLLER_STACK_WORDS, NULL,
        tskIDLE_PRIORITY + 3U, taskCORE_AFFINITY_BIT( 0 ), NULL ) == pdPASS );

    STRESS_PROGRESS( "[stress128] controller created; starting scheduler\n" );

    vTaskStartScheduler();
    configASSERT( 0 );
    return 1;
}
