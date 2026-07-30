/*
 * freertos_test/main.c
 *
 * Comprehensive FreeRTOS test suite scalable from 1 to 64 cores.
 *
 * All sizing constants derive from configNUMBER_OF_CORES so the same
 * source compiles and runs correctly for CORES = 1 ... 64.
 *
 * Tests
 * -----
 *  1. Context-switch stress   - (2xCORES+2) tasks at equal priority;
 *                               counting semaphore (SEM_SLOTS) bounds
 *                               concurrency, mutex serialises counter
 *                               updates; multiple taskYIELD() per loop
 *                               to maximise SMP context switches.
 *
 *  2. Mutex contention        - (2xCORES+2) tasks race for one mutex and
 *                               increment a shared counter.  Final value
 *                               must equal workers x ITER_FAST.
 *
 *  3. Counting-sem + mutex    - Pattern from trace_test.c: each worker
 *                               first acquires a counting semaphore
 *                               (concurrency limit = CORES), yields to
 *                               simulate parallel work in the shared area,
 *                               then acquires a mutex for the single-writer
 *                               critical section.  Demonstrates bounded
 *                               concurrency across cores.
 *
 *  4. Task notifications      - (2xCORES+2) notifier tasks each send
 *                               ITER_FAST notifications to a single
 *                               collector task; collector verifies the
 *                               exact total (cross-core notification storm).
 *
 *  5. Event group             - min(2xCORES+2, 24) tasks each set one
 *                               unique bit after a yield loop; runner waits
 *                               for all bits simultaneously.
 *
 *  6. Queue stress            - (CORES+1) bounded-queue producers and
 *                               (CORES+1) consumers; queue depth = CORES+1
 *                               so it fills quickly, exercising cross-core
 *                               block / unblock wakeup chains.
 *
 *  7. Task priority set       - one low-priority task blocked on a
 *                               semaphore; runner boosts it with
 *                               vTaskPrioritySet() before wake-up so it
 *                               preempts equal-priority fillers; subject
 *                               lowers its own priority before exit
 *                               (exercises traceTASK_PRIORITY_SET).
 *
 *  8. Priority inversion      - low task holds a mutex while medium-
 *                               priority work runs; high task blocks on
 *                               the mutex.  Mutex priority inheritance
 *                               must boost the low task to high while
 *                               the high task waits (t8_inherit_ok).
 *
 *  9. Task suspend/resume     - subject task blocks on a semaphore;
 *                               runner suspends it (vTaskSuspend), then
 *                               satisfies the wait condition and confirms
 *                               it does NOT run until vTaskResume() is
 *                               called (traceTASK_SUSPEND / traceTASK_RESUME).
 *
 * Tests run back-to-back with only taskYIELD() handoffs between phases
 * (no vTaskDelay gaps) so all cores stay busy under SMP load.
 */

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <stdint.h>

#include "FreeRTOS.h"
#include "task.h"
#include "semphr.h"
#include "event_groups.h"
#include "queue.h"

/* ==================================================================
 * Sizing - all derived from configNUMBER_OF_CORES
 * ================================================================== */

/*
 * Workers per test phase.
 *   CORES=1 -> 4   CORES=2 -> 6   CORES=4 -> 10   CORES=8 -> 18
 * Having more tasks than cores keeps every core busy and forces the
 * SMP scheduler to juggle tasks, maximising context-switch pressure.
 */
#define NUM_WORKERS        ( 2 * configNUMBER_OF_CORES + 2 )

/*
 * Counting-semaphore slot limit for test 3.
 * One slot per core means up to CORES tasks are in the shared area at once.
 */
#define SEM_SLOTS          ( configNUMBER_OF_CORES )

/*
 * EventBits_t has at least 24 usable bits on all FreeRTOS platforms.
 * Cap the event-group test workers at 24 so ALL_EV_BITS is always valid.
 */
#if ( NUM_WORKERS <= 24 )
#  define EV_WORKERS       NUM_WORKERS
#else
#  define EV_WORKERS       24
#endif

/* Queue producers == queue consumers == CORES+1 (half of NUM_WORKERS). */
#define Q_HALF             ( NUM_WORKERS / 2 )

/* Iterations scale with core count to keep SMP busy (no vTaskDelay in workers). */
#define ITER_FAST          ( configNUMBER_OF_CORES * 12 )
#define ITER_SLOW          ( configNUMBER_OF_CORES * 6 )

/* Extra yields per test-1 loop (inside/outside mutex). */
#define T1_YIELDS          3

/* Stack depth for worker tasks (words). */
#define TASK_STACK_WORDS   192u

/* Stack depth for the runner task (words). */
#define RUNNER_STACK_WORDS ( TASK_STACK_WORDS * 4 )

/* Task priorities. */
#define RUNNER_PRIORITY    ( configMAX_PRIORITIES - 1 )
#define WORKER_PRIORITY    ( configMAX_PRIORITIES - 2 )
#define LOW_PRIORITY       ( ( WORKER_PRIORITY > 0 ) ? ( WORKER_PRIORITY - 1 ) : 0 )
#define BOOST_PRIORITY     ( WORKER_PRIORITY + 1 )

/* Test 8 — L < M < H (mutex priority inheritance). */
#define INV_LOW_PRIORITY   LOW_PRIORITY
#define INV_MED_PRIORITY   WORKER_PRIORITY
#define INV_HIGH_PRIORITY  BOOST_PRIORITY

/* ==================================================================
 * Application hooks
 * ================================================================== */

void vApplicationStackOverflowHook( TaskHandle_t xTask,
                                     char        *pcTaskName )
{
    (void)xTask;
    printf( "FATAL: stack overflow in task '%s'\n", pcTaskName );
    taskDISABLE_INTERRUPTS();
    for( ;; ) {}
}

/* ==================================================================
 * TEST 1 - Context-switch stress (counting sem + mutex + yields)
 *
 * NUM_WORKERS tasks at equal priority (WORKER_PRIORITY).  Each loop:
 *   (a) Take counting semaphore (max SEM_SLOTS = CORES concurrent tasks).
 *   (b) taskYIELD() T1_YIELDS times (cross-core scheduling pressure).
 *   (c) Take mutex, increment private slot, release mutex.
 *   (d) taskYIELD() T1_YIELDS times again before leaving the shared area.
 *
 * Correctness: each slot must reach exactly ITER_FAST.
 * ================================================================== */

static volatile uint32_t  t1_counts[ NUM_WORKERS ];
static SemaphoreHandle_t  t1_area, t1_mtx, t1_done;

static void vCtxSwitchWorker( void *pvArg )
{
    int slot = (int)(intptr_t)pvArg, i, y;

    for( i = 0; i < ITER_FAST; ++i )
    {
#if configUSE_TRACE_FACILITY
        traceINTERVAL_START(1);
#endif
        xSemaphoreTake( t1_area, portMAX_DELAY );

        for( y = 0; y < T1_YIELDS; ++y )
            taskYIELD();

        xSemaphoreTake( t1_mtx, portMAX_DELAY );
        t1_counts[ slot ]++;
        xSemaphoreGive( t1_mtx );

        for( y = 0; y < T1_YIELDS; ++y )
            taskYIELD();

        xSemaphoreGive( t1_area );
#if configUSE_TRACE_FACILITY
        traceINTERVAL_STOP(1);
#endif
    }
    xSemaphoreGive( t1_done );
    vTaskDelete( NULL );
}

static int run_test1( void )
{
    int i, fail = 0;

    memset( (void *)t1_counts, 0, sizeof t1_counts );
    t1_area = xSemaphoreCreateCounting( SEM_SLOTS, SEM_SLOTS );
    t1_mtx  = xSemaphoreCreateMutex();
    t1_done = xSemaphoreCreateCounting( NUM_WORKERS, 0 );
    configASSERT( t1_area && t1_mtx && t1_done );

    for( i = 0; i < NUM_WORKERS; ++i )
        configASSERT( xTaskCreate( vCtxSwitchWorker, "CS",
                                   TASK_STACK_WORDS, (void *)(intptr_t)i,
                                   WORKER_PRIORITY, NULL ) == pdPASS );

    for( i = 0; i < NUM_WORKERS; ++i )
        xSemaphoreTake( t1_done, portMAX_DELAY );

    vSemaphoreDelete( t1_area );
    vSemaphoreDelete( t1_mtx );
    vSemaphoreDelete( t1_done );

    for( i = 0; i < NUM_WORKERS; ++i )
    {
        if( t1_counts[ i ] != (uint32_t)ITER_FAST )
        {
            printf( "  FAIL slot %d: got %u want %d\n",
                    i, (unsigned)t1_counts[ i ], ITER_FAST );
            ++fail;
        }
    }
    return fail;
}

/* ==================================================================
 * TEST 2 - Mutex contention
 *
 * NUM_WORKERS tasks race for a single mutex and each increment a
 * shared counter ITER_FAST times.  The mutex serialises all writes;
 * on SMP, cores spin on the underlying spinlock while another core
 * holds the mutex.
 *
 * Correctness: t2_ctr == NUM_WORKERS x ITER_FAST.
 * ================================================================== */

static volatile uint32_t  t2_ctr;
static SemaphoreHandle_t  t2_mtx, t2_done;

static void vMutexWorker( void *pvArg )
{
    int i;
    (void)pvArg;

    for( i = 0; i < ITER_FAST; ++i )
    {
#if configUSE_TRACE_FACILITY
        traceINTERVAL_START(2);
#endif
        xSemaphoreTake( t2_mtx, portMAX_DELAY );
        t2_ctr++;
        xSemaphoreGive( t2_mtx );
        taskYIELD();
#if configUSE_TRACE_FACILITY
        traceINTERVAL_STOP(2);
#endif
    }
    xSemaphoreGive( t2_done );
    vTaskDelete( NULL );
}

static int run_test2( void )
{
    int i, fail = 0;

    t2_ctr  = 0;
    t2_mtx  = xSemaphoreCreateMutex();
    t2_done = xSemaphoreCreateCounting( NUM_WORKERS, 0 );
    configASSERT( t2_mtx && t2_done );

    for( i = 0; i < NUM_WORKERS; ++i )
        configASSERT( xTaskCreate( vMutexWorker, "MX",
                                   TASK_STACK_WORDS, NULL,
                                   WORKER_PRIORITY, NULL ) == pdPASS );

    for( i = 0; i < NUM_WORKERS; ++i )
        xSemaphoreTake( t2_done, portMAX_DELAY );

    vSemaphoreDelete( t2_mtx );
    vSemaphoreDelete( t2_done );

    uint32_t exp = (uint32_t)( NUM_WORKERS * ITER_FAST );
    if( t2_ctr != exp )
    {
        printf( "  FAIL: ctr=%u want=%u\n", (unsigned)t2_ctr, (unsigned)exp );
        ++fail;
    }
    return fail;
}

/* ==================================================================
 * TEST 3 - Counting semaphore + mutex   (trace_test.c pattern)
 *
 * Each worker:
 *   (a) Takes a counting semaphore (max = SEM_SLOTS = CORES):
 *       at most CORES tasks may be inside the "shared area" at once.
 *   (b) Calls taskYIELD() to simulate parallel work inside the area.
 *   (c) Takes a mutex for the critical section and increments t3_ctr.
 *   (d) Releases mutex then counting semaphore to leave the area.
 *
 * This is the key pattern from trace_test.c: concurrency limited by
 * the semaphore, serialisation within that concurrency by the mutex.
 * On SMP, up to CORES tasks execute step (b) in parallel across cores
 * while only one holds the mutex at any instant.
 *
 * Correctness: t3_ctr == NUM_WORKERS x ITER_SLOW.
 * ================================================================== */

static volatile uint32_t  t3_ctr;
static SemaphoreHandle_t  t3_area, t3_mtx, t3_done;

static void vSemMutexWorker( void *pvArg )
{
    int i;
    (void)pvArg;

    for( i = 0; i < ITER_SLOW; ++i )
    {
#if configUSE_TRACE_FACILITY
        traceINTERVAL_START(3);
#endif
        /* -- Enter shared area (max SEM_SLOTS concurrent tasks) -- */
        xSemaphoreTake( t3_area, portMAX_DELAY );

        /* Simulate parallel work inside the shared area. */
        taskYIELD();
        taskYIELD();

        /* -- Critical section: single writer -- */
        xSemaphoreTake( t3_mtx, portMAX_DELAY );
        t3_ctr++;
        xSemaphoreGive( t3_mtx );

        /* -- Leave shared area -- */
        xSemaphoreGive( t3_area );
#if configUSE_TRACE_FACILITY
        traceINTERVAL_STOP(3);
#endif
    }
    xSemaphoreGive( t3_done );
    vTaskDelete( NULL );
}

static int run_test3( void )
{
    int i, fail = 0;

    t3_ctr  = 0;
    t3_area = xSemaphoreCreateCounting( SEM_SLOTS, SEM_SLOTS );
    t3_mtx  = xSemaphoreCreateMutex();
    t3_done = xSemaphoreCreateCounting( NUM_WORKERS, 0 );
    configASSERT( t3_area && t3_mtx && t3_done );

    for( i = 0; i < NUM_WORKERS; ++i )
        configASSERT( xTaskCreate( vSemMutexWorker, "SM",
                                   TASK_STACK_WORDS, NULL,
                                   WORKER_PRIORITY, NULL ) == pdPASS );

    for( i = 0; i < NUM_WORKERS; ++i )
        xSemaphoreTake( t3_done, portMAX_DELAY );

    vSemaphoreDelete( t3_area );
    vSemaphoreDelete( t3_mtx );
    vSemaphoreDelete( t3_done );

    uint32_t exp = (uint32_t)( NUM_WORKERS * ITER_SLOW );
    if( t3_ctr != exp )
    {
        printf( "  FAIL: ctr=%u want=%u\n", (unsigned)t3_ctr, (unsigned)exp );
        ++fail;
    }
    return fail;
}

/* ==================================================================
 * TEST 4 - Task notifications (cross-core notification storm)
 *
 * A single collector task receives ITER_FAST notifications from each
 * of NUM_WORKERS notifier tasks (total = NUM_WORKERS x ITER_FAST).
 * Each notifier sends xTaskNotifyGive() then yields, creating a
 * burst of concurrent notifications from multiple cores.
 *
 * ulTaskNotifyTake(pdFALSE) decrements the notification value by 1
 * per call, correctly counting each individual notification even when
 * multiple have accumulated.
 *
 * Correctness: t4_received == NUM_WORKERS x ITER_FAST.
 * ================================================================== */

static TaskHandle_t       t4_collector;
static SemaphoreHandle_t  t4_ndone, t4_cdone;
static volatile uint32_t  t4_received;

static void vNotifyCollector( void *pvArg )
{
    uint32_t exp = (uint32_t)( NUM_WORKERS * ITER_FAST );
    (void)pvArg;

    t4_received = 0;
    while( t4_received < exp )
    {
        ulTaskNotifyTake( pdFALSE, portMAX_DELAY );
        t4_received++;
    }
    xSemaphoreGive( t4_cdone );
    vTaskDelete( NULL );
}

static void vNotifyWorker( void *pvArg )
{
    int i;
    (void)pvArg;

    for( i = 0; i < ITER_FAST; ++i )
    {
#if configUSE_TRACE_FACILITY
        traceINTERVAL_START(4);
#endif
        xTaskNotifyGive( t4_collector );
        taskYIELD();
#if configUSE_TRACE_FACILITY
        traceINTERVAL_STOP(4);
#endif
    }
    xSemaphoreGive( t4_ndone );
    vTaskDelete( NULL );
}

static int run_test4( void )
{
    int i, fail = 0;

    t4_ndone = xSemaphoreCreateCounting( NUM_WORKERS, 0 );
    t4_cdone = xSemaphoreCreateBinary();
    configASSERT( t4_ndone && t4_cdone );

    /* Collector must exist before notifiers so t4_collector is valid. */
    configASSERT( xTaskCreate( vNotifyCollector, "NC",
                               TASK_STACK_WORDS, NULL,
                               WORKER_PRIORITY, &t4_collector ) == pdPASS );

    for( i = 0; i < NUM_WORKERS; ++i )
        configASSERT( xTaskCreate( vNotifyWorker, "NW",
                                   TASK_STACK_WORDS, NULL,
                                   WORKER_PRIORITY, NULL ) == pdPASS );

    /* Wait for all notifiers to finish sending. */
    for( i = 0; i < NUM_WORKERS; ++i )
        xSemaphoreTake( t4_ndone, portMAX_DELAY );

    /* Wait for the collector to drain any accumulated notifications. */
    xSemaphoreTake( t4_cdone, portMAX_DELAY );

    vSemaphoreDelete( t4_ndone );
    vSemaphoreDelete( t4_cdone );

    uint32_t exp = (uint32_t)( NUM_WORKERS * ITER_FAST );
    if( t4_received != exp )
    {
        printf( "  FAIL: rcvd=%u want=%u\n", (unsigned)t4_received, (unsigned)exp );
        ++fail;
    }
    return fail;
}

/* ==================================================================
 * TEST 5 - Event group (all-bits synchronisation barrier)
 *
 * EV_WORKERS tasks each do a yield loop (ITER_FAST times) to simulate
 * independent work, then atomically set their unique bit in a shared
 * event group.  The runner calls xEventGroupWaitBits() with wait-for-
 * all, blocking until the very last task sets its bit.
 *
 * On SMP, multiple tasks set bits from different cores simultaneously,
 * exercising the kernel's atomic bit-set and the wait-for-all path.
 *
 * Correctness: all EV_WORKERS bits must be set.
 * ================================================================== */

#define ALL_EV_BITS  ( (EventBits_t)( ( (EventBits_t)1 << EV_WORKERS ) - 1UL ) )

static EventGroupHandle_t t5_eg;

static void vEventWorker( void *pvArg )
{
    int bit = (int)(intptr_t)pvArg, i;

    for( i = 0; i < ITER_FAST; ++i )
    {
#if configUSE_TRACE_FACILITY
        traceINTERVAL_START(5);
#endif
        taskYIELD();
#if configUSE_TRACE_FACILITY
        traceINTERVAL_STOP(5);
#endif
    }

    taskYIELD();

    xEventGroupSetBits( t5_eg, (EventBits_t)( (EventBits_t)1 << bit ) );
    vTaskDelete( NULL );
}

static int run_test5( void )
{
    int i;

    t5_eg = xEventGroupCreate();
    configASSERT( t5_eg );

    for( i = 0; i < EV_WORKERS; ++i )
        configASSERT( xTaskCreate( vEventWorker, "EV",
                                   TASK_STACK_WORDS, (void *)(intptr_t)i,
                                   WORKER_PRIORITY, NULL ) == pdPASS );

    EventBits_t bits = xEventGroupWaitBits( t5_eg, ALL_EV_BITS,
                                            pdTRUE,  /* clear on exit  */
                                            pdTRUE,  /* wait for ALL   */
                                            portMAX_DELAY );
    vEventGroupDelete( t5_eg );

    if( ( bits & ALL_EV_BITS ) != ALL_EV_BITS )
    {
        printf( "  FAIL: bits=0x%x want=0x%x\n",
                (unsigned)bits, (unsigned)ALL_EV_BITS );
        return 1;
    }
    return 0;
}

/* ==================================================================
 * TEST 6 - Queue stress (bounded producer / consumer)
 *
 * Q_HALF producer tasks each send ITER_FAST items; Q_HALF consumer
 * tasks each receive ITER_FAST items.  Queue depth = Q_HALF so the
 * queue fills quickly, forcing producers to block.  When a consumer
 * drains an item, a blocked producer on another core wakes up; these
 * cross-core wakeup chains stress the queue's lock implementation.
 *
 * Total items sent  = Q_HALF x ITER_FAST
 * Total items recvd = Q_HALF x ITER_FAST  (must balance for all
 *                     consumers to complete their ITER_FAST loops)
 *
 * Correctness: no deadlock - if all Q_HALF*2 tasks signal t6_done
 * the test passes; a hang here means the queue mechanism is broken.
 * ================================================================== */

static QueueHandle_t      t6_q;
static SemaphoreHandle_t  t6_done;

static void vQProd( void *pvArg )
{
    int i;
    (void)pvArg;

    for( i = 0; i < ITER_FAST; ++i )
    {
#if configUSE_TRACE_FACILITY
        traceINTERVAL_START(6);
#endif
        uint32_t v = (uint32_t)i;
        xQueueSend( t6_q, &v, portMAX_DELAY );
#if configUSE_TRACE_FACILITY
        traceINTERVAL_STOP(6);
#endif
    }
    xSemaphoreGive( t6_done );
    vTaskDelete( NULL );
}

static void vQCons( void *pvArg )
{
    int i;
    (void)pvArg;

    for( i = 0; i < ITER_FAST; ++i )
    {
        uint32_t v;
        xQueueReceive( t6_q, &v, portMAX_DELAY );
    }
    xSemaphoreGive( t6_done );
    vTaskDelete( NULL );
}

static int run_test6( void )
{
    int i;

    /* Queue depth = Q_HALF: fills after Q_HALF items, forcing block/wake. */
    t6_q    = xQueueCreate( Q_HALF, sizeof( uint32_t ) );
    t6_done = xSemaphoreCreateCounting( Q_HALF * 2, 0 );
    configASSERT( t6_q && t6_done );

    for( i = 0; i < Q_HALF; ++i )
        configASSERT( xTaskCreate( vQProd, "QP",
                                   TASK_STACK_WORDS, NULL,
                                   WORKER_PRIORITY, NULL ) == pdPASS );
    for( i = 0; i < Q_HALF; ++i )
        configASSERT( xTaskCreate( vQCons, "QC",
                                   TASK_STACK_WORDS, NULL,
                                   WORKER_PRIORITY, NULL ) == pdPASS );

    /* Wait for all producers and consumers to complete. */
    for( i = 0; i < Q_HALF * 2; ++i )
        xSemaphoreTake( t6_done, portMAX_DELAY );

    vQueueDelete( t6_q );
    vSemaphoreDelete( t6_done );
    return 0;   /* reaching here means no deadlock */
}

/* ==================================================================
 * TEST 7 - Task priority set (vTaskPrioritySet / traceTASK_PRIORITY_SET)
 *
 * One subject task starts at LOW_PRIORITY and blocks on t7_go.
 * NUM_WORKERS filler tasks at WORKER_PRIORITY spin with taskYIELD() so
 * cores stay busy.  The runner (run_test7, executing as the Runner task)
 * calls vTaskPrioritySet( subject, BOOST_PRIORITY ) then posts t7_go.
 * The subject must observe the boosted priority, increment t7_ctr, call
 * vTaskPrioritySet( NULL, LOW_PRIORITY ) on itself, and signal done.
 *
 * Correctness: t7_ctr == 1 and t7_pri_ok == 1.
 * ================================================================== */

static TaskHandle_t       t7_subject;
static SemaphoreHandle_t  t7_go, t7_done;
static volatile uint32_t  t7_ctr;
static volatile uint32_t  t7_pri_ok;

static void vPriFiller( void *pvArg )
{
    int i;
    (void)pvArg;

    for( i = 0; i < ITER_SLOW; ++i )
        taskYIELD();

    vTaskDelete( NULL );
}

static void vPriSubject( void *pvArg )
{
    (void)pvArg;

    xSemaphoreTake( t7_go, portMAX_DELAY );

    if( uxTaskPriorityGet( NULL ) == BOOST_PRIORITY )
        t7_pri_ok = 1;

    t7_ctr++;
    vTaskPrioritySet( NULL, LOW_PRIORITY );
    xSemaphoreGive( t7_done );
    vTaskDelete( NULL );
}

static int run_test7( void )
{
    int i, fail = 0;

    t7_ctr    = 0;
    t7_pri_ok = 0;
    t7_go     = xSemaphoreCreateBinary();
    t7_done   = xSemaphoreCreateBinary();
    configASSERT( t7_go && t7_done );

    configASSERT( xTaskCreate( vPriSubject, "PS",
                               TASK_STACK_WORDS, NULL,
                               LOW_PRIORITY, &t7_subject ) == pdPASS );

    for( i = 0; i < NUM_WORKERS; ++i )
        configASSERT( xTaskCreate( vPriFiller, "PF",
                                   TASK_STACK_WORDS, NULL,
                                   WORKER_PRIORITY, NULL ) == pdPASS );

    /* Let the subject block and fillers start running. */
    for( i = 0; i < (int)configNUMBER_OF_CORES; ++i )
        taskYIELD();

#if configUSE_TRACE_FACILITY
    traceINTERVAL_START( 7 );
#endif
    vTaskPrioritySet( t7_subject, BOOST_PRIORITY );
    xSemaphoreGive( t7_go );
    xSemaphoreTake( t7_done, portMAX_DELAY );
#if configUSE_TRACE_FACILITY
    traceINTERVAL_STOP( 7 );
#endif

    vSemaphoreDelete( t7_go );
    vSemaphoreDelete( t7_done );

    if( t7_ctr != 1 )
    {
        printf( "  FAIL: ctr=%u want 1\n", (unsigned)t7_ctr );
        ++fail;
    }
    if( t7_pri_ok != 1 )
    {
        printf( "  FAIL: subject did not run at boosted priority %d\n",
                (int)BOOST_PRIORITY );
        ++fail;
    }
    return fail;
}

/* ==================================================================
 * TEST 8 - Priority inversion (mutex priority inheritance)
 *
 * Classic L/M/H scenario on a mutex with inheritance enabled:
 *   L (low)  takes the mutex and spins with taskYIELD().
 *   M (med)  runs CPU work once the mutex is held (would block H in a
 *            non-inheritance inversion).
 *   H (high) blocks on the mutex; the kernel must boost L to H.
 *
 * L records t8_inherit_ok when uxTaskPriorityGet() == INV_HIGH_PRIORITY
 * during the hold loop.  H signals t8_h_done after it acquires the mutex.
 *
 * Correctness: t8_inherit_ok == 1 and high task completes.
 * ================================================================== */

static SemaphoreHandle_t  t8_mtx, t8_l_ready, t8_h_done;
static volatile uint32_t  t8_inherit_ok;

static void vInvLow( void *pvArg )
{
    int i;
    (void)pvArg;

    xSemaphoreTake( t8_mtx, portMAX_DELAY );
    xSemaphoreGive( t8_l_ready );
    xSemaphoreGive( t8_l_ready );

    for( i = 0; i < ITER_SLOW * 4; ++i )
    {
        if( uxTaskPriorityGet( NULL ) == (UBaseType_t)INV_HIGH_PRIORITY )
            t8_inherit_ok = 1;

        taskYIELD();
    }

    xSemaphoreGive( t8_mtx );
    vTaskDelete( NULL );
}

static void vInvHigh( void *pvArg )
{
    (void)pvArg;

    xSemaphoreTake( t8_l_ready, portMAX_DELAY );
    xSemaphoreTake( t8_mtx, portMAX_DELAY );
    xSemaphoreGive( t8_h_done );
    vTaskDelete( NULL );
}

static void vInvMed( void *pvArg )
{
    int i;
    (void)pvArg;

    xSemaphoreTake( t8_l_ready, portMAX_DELAY );

    for( i = 0; i < ITER_FAST * 4; ++i )
        taskYIELD();

    vTaskDelete( NULL );
}

static int run_test8( void )
{
    int fail = 0;

    t8_inherit_ok = 0;
    t8_mtx        = xSemaphoreCreateMutex();
    t8_l_ready    = xSemaphoreCreateCounting( 2, 0 );
    t8_h_done     = xSemaphoreCreateBinary();
    configASSERT( t8_mtx && t8_l_ready && t8_h_done );

    configASSERT( xTaskCreate( vInvLow, "IL",
                               TASK_STACK_WORDS, NULL,
                               INV_LOW_PRIORITY, NULL ) == pdPASS );
    configASSERT( xTaskCreate( vInvHigh, "IH",
                               TASK_STACK_WORDS, NULL,
                               INV_HIGH_PRIORITY, NULL ) == pdPASS );
    configASSERT( xTaskCreate( vInvMed, "IM",
                               TASK_STACK_WORDS, NULL,
                               INV_MED_PRIORITY, NULL ) == pdPASS );

#if configUSE_TRACE_FACILITY
    traceINTERVAL_START( 8 );
#endif
    xSemaphoreTake( t8_h_done, portMAX_DELAY );
#if configUSE_TRACE_FACILITY
    traceINTERVAL_STOP( 8 );
#endif

    vSemaphoreDelete( t8_mtx );
    vSemaphoreDelete( t8_l_ready );
    vSemaphoreDelete( t8_h_done );

    if( t8_inherit_ok != 1 )
    {
        printf( "  FAIL: mutex holder was not boosted to priority %d\n",
                (int)INV_HIGH_PRIORITY );
        ++fail;
    }
    return fail;
}

/* ==================================================================
 * TEST 9 - Task suspend / resume (vTaskSuspend / vTaskResume)
 *
 * The subject task increments t9_ctr to 1, signals t9_started, then
 * blocks on t9_go.  The runner:
 *   (a) waits for t9_started so the subject is known to be blocked;
 *   (b) calls vTaskSuspend() on the already-blocked subject;
 *   (c) gives t9_go - the subject's wait condition is now satisfied,
 *       but it must stay suspended and NOT run;
 *   (d) yields with NUM_WORKERS fillers ready on every core - t9_ctr
 *       must stay at 1;
 *   (e) calls vTaskResume() - the subject must now wake, set t9_ctr to
 *       2, and signal t9_done.
 *
 * The subject runs at BOOST_PRIORITY (strictly above the WORKER_PRIORITY
 * fillers), same as test 7's boosted subject - this guarantees the SMP
 * scheduler immediately preempts a filler-busy core on resume instead of
 * waiting for same-priority round-robin, which is what made this test
 * slow when subject and fillers shared WORKER_PRIORITY.
 *
 * Correctness: t9_ctr == 1 right after suspend (unchanged while
 * suspended) and t9_ctr == 2 after resume + completion.
 * ================================================================== */

static SemaphoreHandle_t  t9_started, t9_go, t9_done;
static volatile uint32_t  t9_ctr;

static void vSuspResSubject( void *pvArg )
{
    (void)pvArg;

    t9_ctr = 1;
    xSemaphoreGive( t9_started );
    xSemaphoreTake( t9_go, portMAX_DELAY );
    t9_ctr = 2;
    xSemaphoreGive( t9_done );
    vTaskDelete( NULL );
}

static void vSuspResFiller( void *pvArg )
{
    int i;
    (void)pvArg;

    for( i = 0; i < ITER_SLOW; ++i )
        taskYIELD();

    vTaskDelete( NULL );
}

static int run_test9( void )
{
    TaskHandle_t subject;
    int i, fail = 0;

    t9_ctr     = 0;
    t9_started = xSemaphoreCreateBinary();
    t9_go      = xSemaphoreCreateBinary();
    t9_done    = xSemaphoreCreateBinary();
    configASSERT( t9_started && t9_go && t9_done );

    configASSERT( xTaskCreate( vSuspResSubject, "SR",
                               TASK_STACK_WORDS, NULL,
                               BOOST_PRIORITY, &subject ) == pdPASS );

    for( i = 0; i < NUM_WORKERS; ++i )
        configASSERT( xTaskCreate( vSuspResFiller, "SF",
                                   TASK_STACK_WORDS, NULL,
                                   WORKER_PRIORITY, NULL ) == pdPASS );

    /* Wait for the subject to run once and block on t9_go. */
    xSemaphoreTake( t9_started, portMAX_DELAY );

#if configUSE_TRACE_FACILITY
    traceINTERVAL_START(9);
#endif
    vTaskSuspend( subject );

    /* Satisfy the subject's wait condition while it is suspended - it
     * must NOT run even though t9_go is now available. */
    xSemaphoreGive( t9_go );

    for( i = 0; i < (int)configNUMBER_OF_CORES; ++i )
        taskYIELD();

    if( t9_ctr != 1 )
    {
        printf( "  FAIL: subject ran while suspended (ctr=%u want 1)\n",
                (unsigned)t9_ctr );
        ++fail;
    }

    vTaskResume( subject );
    xSemaphoreTake( t9_done, portMAX_DELAY );
#if configUSE_TRACE_FACILITY
    traceINTERVAL_STOP(9);
#endif

    vSemaphoreDelete( t9_started );
    vSemaphoreDelete( t9_go );
    vSemaphoreDelete( t9_done );

    if( t9_ctr != 2 )
    {
        printf( "  FAIL: subject did not resume/complete (ctr=%u want 2)\n",
                (unsigned)t9_ctr );
        ++fail;
    }
    return fail;
}

/* ==================================================================
 * Test-runner task
 * ================================================================== */

typedef int (*test_fn_t)( void );

typedef struct
{
    const char  *name;
    test_fn_t    fn;
} test_entry_t;

static const test_entry_t tests[] =
{
    { "1: context-switch stress",  run_test1 },
    { "2: mutex contention",       run_test2 },
    { "3: counting-sem + mutex",   run_test3 },
    { "4: task notifications",     run_test4 },
    { "5: event group",            run_test5 },
    { "6: queue stress",           run_test6 },
    { "7: task priority set",      run_test7 },
    { "8: priority inversion",     run_test8 },
    { "9: task suspend/resume",    run_test9 },
};

#define N_TESTS  ( (int)( sizeof( tests ) / sizeof( tests[ 0 ] ) ) )

/* Brief yield handoff between phases (no vTaskDelay idle gaps). */
static void prvPhaseHandoff( void )
{
    int i;

    for( i = 0; i < (int)configNUMBER_OF_CORES; ++i )
        taskYIELD();
}

static void vTestRunner( void *pvArg )
{
    int total_fail = 0, i;
    (void)pvArg;

    printf( "freertos_test: starting\n" );
    printf( "  cores=%-2d  workers=%-3d  sem_slots=%-2d"
            "  iter_fast=%-3d  iter_slow=%d  t1_yields=%d\n",
            configNUMBER_OF_CORES, NUM_WORKERS, SEM_SLOTS,
            ITER_FAST, ITER_SLOW, T1_YIELDS );

    for( i = 0; i < N_TESTS; ++i )
    {
        int prev = total_fail;
        printf( "test %-30s ... ", tests[ i ].name );
        fflush( stdout );
#if configUSE_TRACE_FACILITY
        traceINTERVAL_START(0);
#endif
        total_fail += tests[ i ].fn();
#if configUSE_TRACE_FACILITY
        traceINTERVAL_STOP(0);
#endif
        printf( "%s\n", ( total_fail == prev ) ? "pass" : "FAIL" );
        prvPhaseHandoff();
    }

#if configUSE_TRACE_FACILITY
    traceEND();
#endif

    if( total_fail == 0 )
    {
        printf( "freertos_test: all tests passed\n" );
        exit( 0 );
    }
    else
    {
        printf( "freertos_test: %d test(s) FAILED\n", total_fail );
        exit( 1 );
    }
}

#if configUSE_TICK_HOOK
/*
 * Tick hook — sample heap usage every RTOS tick (see configTICK_RATE_HZ).
 *
 * Requires configUSE_TICK_HOOK = 1 in FreeRTOSConfig.h and heap_4.c linked
 * into the build (the demo Makefile already selects heap_4.c).
 *
 * xPortGetFreeHeapSize() reports free bytes in the heap_4 pool; subtracting
 * from configTOTAL_HEAP_SIZE yields bytes currently allocated by tasks,
 * queues, semaphores, etc.
 *
 * btf_traceTAG( 0, bytes ) appends an STI tag0_event to the trace buffer
 * (configINCLUDE_TAGS must be 1 — default in FreeRTOS-Trace.h).  After
 * `make run`, open tracedata/trace.btf in BTFViewer and expand the
 * tag0_event row to plot allocated heap over time.
 *
 * Eight tag channels (0–7) are available via btf_traceTAG( n, value ).
 */
void vApplicationTickHook( void )
{
#if configUSE_TRACE_FACILITY
    size_t total_heap = configTOTAL_HEAP_SIZE;
    size_t free_heap  = xPortGetFreeHeapSize();
    size_t currently_allocated_bytes = total_heap - free_heap;

    btf_traceTAG( 0, (int) currently_allocated_bytes );
#endif
}
#endif

/* ==================================================================
 * main
 *
 * Hart 0: installs trap handler, creates runner task, starts scheduler.
 * Harts 1..N-1 (SMP): call vPortSecondaryHartEntry() which waits for
 *   the scheduler and then runs tasks on that core.
 * ================================================================== */

extern void freertos_risc_v_trap_handler( void );

static inline void prvWriteMtvec( void (*handler)(void) )
{
    __asm__ volatile( "csrw mtvec, %0" : : "r"( (uintptr_t)handler ) : "memory" );
}

int main( void )
{
    /* Hart 0 only — secondary harts are dispatched to vPortSecondaryHartEntry
     * directly from crt0.S and never reach main(). */
    prvWriteMtvec( freertos_risc_v_trap_handler );

#if configUSE_TRACE_FACILITY
    /* Enable trace capture before any traced tasks are created.  traceEND() is
     * called from vTestRunner when all tests finish (writes trace.bin). */
    traceSTART();
#endif

    configASSERT( xTaskCreate( vTestRunner, "Runner",
                               RUNNER_STACK_WORDS, NULL,
                               RUNNER_PRIORITY, NULL ) == pdPASS );
    vTaskStartScheduler();
    for( ;; ) {}
}
