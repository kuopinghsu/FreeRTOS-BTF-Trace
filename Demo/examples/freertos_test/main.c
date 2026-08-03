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
 *  8. Priority inversion      - textbook L/M/H on one core, repeated
 *                               T8_ROUNDS times: each round Low holds a
 *                               mutex, Med runs mid-priority work, High
 *                               blocks, and inheritance boosts Low→High
 *                               (multiple red stripes on Low in BTFViewer).
 *                               Tasks named Low/Med/High, pinned to core 0
 *                               on SMP so the geometry is unambiguous.
 *
 *  9. Task suspend/resume     - several subjects (up to 4, pinned across
 *                               cores on SMP) each run T9_ROUNDS of:
 *                               (a) suspend-while-blocked — wait satisfied
 *                               under suspend must not run; then resume;
 *                               (b) suspend-while-running — busy subject
 *                               frozen mid-spin, then resume.  Short sync
 *                               only (no long delays) so 8-core sims stay
 *                               fast while Task Lifecycle shows many
 *                               suspend/resume STI pairs.
 *
 * 10. Core affinity           - SMP only (no-op pass on 1 core): pin one
 *                               task per core via xTaskCreateAffinitySet /
 *                               vTaskCoreAffinitySet; verify portGET_CORE_ID
 *                               stays on-mask; migrate one task from core 0
 *                               to the last core (affinity STI for BTFViewer).
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

/* Test 8 — L < M < H (mutex priority inheritance), repeated rounds. */
#define INV_LOW_PRIORITY   LOW_PRIORITY
#define INV_MED_PRIORITY   WORKER_PRIORITY
#define INV_HIGH_PRIORITY  BOOST_PRIORITY

/* Several inherit episodes so Priority Inheritance charts / timeline
 * stripes are obvious (not a single one-shot boost). */
#define T8_ROUNDS          3

/* Per-round work: long enough for a clear Med preemption + boost window. */
#define T8_LOW_HOLD_ITERS  ( ITER_SLOW * 5 )
#define T8_MED_WORK_ITERS  ( ITER_FAST * 4 )
#define T8_BUSY_SPIN       400
#define T8_MED_SEEN_AT     ( T8_MED_WORK_ITERS / 4 )

/* Test 9 — multi-subject suspend/resume for a rich STI timeline.
 * Cap subjects at 4 so CORES=8 stays quick (sync + few yields only). */
#if ( configNUMBER_OF_CORES > 1 )
#  if ( configNUMBER_OF_CORES < 4 )
#    define T9_SUBJECTS    configNUMBER_OF_CORES
#  else
#    define T9_SUBJECTS    4
#  endif
#else
#  define T9_SUBJECTS      1
#endif
#define T9_ROUNDS          2
#define T9_FILLERS         ( configNUMBER_OF_CORES )

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
 * Textbook single-core L / M / H geometry (pinned to Core_0 on SMP),
 * repeated T8_ROUNDS times so BTFViewer shows multiple red boost stripes
 * and several Priority Inheritance scatter points:
 *
 *   pri H  High  ─── waits for mutex ────────────────────────────┐
 *   pri M  Med   ─── CPU work while Low held the lock ──────────┤
 *   pri L  Low   ─── holds mutex ──► boosted to H (inherit) ────┘
 *
 * Each round:
 *   1. Low takes the mutex (signals lock-held).
 *   2. Runner releases Med → Med preempts Low on the same core.
 *   3. Runner releases High → High blocks → priority_inherit on Low.
 *   4. Low finishes the critical section, gives the mutex.
 *   5. High acquires, signals done, gives back; runner arms the next round.
 *
 * Correctness: every round observes inheritance (t8_inherit_rounds ==
 * T8_ROUNDS) and High completes each round.
 * ================================================================== */

static SemaphoreHandle_t  t8_mtx, t8_lock_held, t8_med_go, t8_med_seen,
                          t8_med_done, t8_high_go, t8_h_done, t8_next_round;
static volatile uint32_t  t8_inherit_ok;
static volatile uint32_t  t8_inherit_rounds;
static volatile uint32_t  t8_med_iters;

/* Small busy+yield chunk so each scheduling quantum leaves a solid bar. */
static void prvT8BusyYield( void )
{
    int j;
    volatile uint32_t sink = 0;

    for( j = 0; j < T8_BUSY_SPIN; ++j )
        sink += ( uint32_t )j;
    taskYIELD();
}

static BaseType_t prvT8Create( TaskFunction_t fn, const char *name,
                               UBaseType_t pri )
{
    /* Pin L/M/H onto core 0 so Med actually preempts Low on the same
     * timeline row geometry viewers expect for classic inversion. */
#if ( configNUMBER_OF_CORES > 1 ) && ( configUSE_CORE_AFFINITY == 1 )
    return xTaskCreateAffinitySet( fn, name, TASK_STACK_WORDS, NULL, pri,
                                   ( UBaseType_t )( 1u << 0 ), NULL );
#else
    return xTaskCreate( fn, name, TASK_STACK_WORDS, NULL, pri, NULL );
#endif
}

static void vInvLow( void *pvArg )
{
    int round, i;
    (void)pvArg;

    for( round = 0; round < T8_ROUNDS; ++round )
    {
        uint32_t saw_boost = 0;

        xSemaphoreTake( t8_mtx, portMAX_DELAY );
        xSemaphoreGive( t8_lock_held );

        for( i = 0; i < T8_LOW_HOLD_ITERS; ++i )
        {
            if( uxTaskPriorityGet( NULL ) == ( UBaseType_t )INV_HIGH_PRIORITY )
            {
                if( saw_boost == 0 )
                {
                    saw_boost = 1;
                    t8_inherit_rounds++;
                }
                t8_inherit_ok = 1;
            }
            prvT8BusyYield();
        }

        xSemaphoreGive( t8_mtx );

        /* Wait for High to finish this round before retaking the mutex. */
        if( round + 1 < T8_ROUNDS )
            xSemaphoreTake( t8_next_round, portMAX_DELAY );
    }

    vTaskDelete( NULL );
}

static void vInvMed( void *pvArg )
{
    int round, i;
    (void)pvArg;

    for( round = 0; round < T8_ROUNDS; ++round )
    {
        xSemaphoreTake( t8_med_go, portMAX_DELAY );
        t8_med_iters = 0;

        for( i = 0; i < T8_MED_WORK_ITERS; ++i )
        {
            t8_med_iters++;
            if( t8_med_iters == ( uint32_t )T8_MED_SEEN_AT )
                xSemaphoreGive( t8_med_seen );
            prvT8BusyYield();
        }

        /* Let the runner (and Low) proceed to the next round without Med
         * monopolising the core after the inherit window ends. */
        xSemaphoreGive( t8_med_done );
    }

    vTaskDelete( NULL );
}

static void vInvHigh( void *pvArg )
{
    int round;
    (void)pvArg;

    for( round = 0; round < T8_ROUNDS; ++round )
    {
        xSemaphoreTake( t8_high_go, portMAX_DELAY );
        /* Blocks here → kernel priority-inherits Low up to INV_HIGH_PRIORITY. */
        xSemaphoreTake( t8_mtx, portMAX_DELAY );
        xSemaphoreGive( t8_h_done );
        xSemaphoreGive( t8_mtx );
    }

    vTaskDelete( NULL );
}

static int run_test8( void )
{
    int round, fail = 0;

    t8_inherit_ok     = 0;
    t8_inherit_rounds = 0;
    t8_med_iters      = 0;
    t8_mtx            = xSemaphoreCreateMutex();
    t8_lock_held      = xSemaphoreCreateBinary();
    t8_med_go         = xSemaphoreCreateBinary();
    t8_med_seen       = xSemaphoreCreateBinary();
    t8_med_done       = xSemaphoreCreateBinary();
    t8_high_go        = xSemaphoreCreateBinary();
    t8_h_done         = xSemaphoreCreateBinary();
    t8_next_round     = xSemaphoreCreateBinary();
    configASSERT( t8_mtx && t8_lock_held && t8_med_go && t8_med_seen &&
                  t8_med_done && t8_high_go && t8_h_done && t8_next_round );

    configASSERT( prvT8Create( vInvLow,  "Low",  INV_LOW_PRIORITY  ) == pdPASS );
    configASSERT( prvT8Create( vInvMed,  "Med",  INV_MED_PRIORITY  ) == pdPASS );
    configASSERT( prvT8Create( vInvHigh, "High", INV_HIGH_PRIORITY ) == pdPASS );

#if configUSE_TRACE_FACILITY
    traceINTERVAL_START( 8 );
#endif

    for( round = 0; round < T8_ROUNDS; ++round )
    {
        /* Phase 1 — Low owns the mutex. */
        xSemaphoreTake( t8_lock_held, portMAX_DELAY );

        /* Phase 2 — Med runs while Low still holds (runner blocks so Med
         * can run despite the runner's higher priority). */
        xSemaphoreGive( t8_med_go );
        xSemaphoreTake( t8_med_seen, portMAX_DELAY );

        /* Phase 3 — High blocks → inheritance boosts Low. */
        xSemaphoreGive( t8_high_go );
        xSemaphoreTake( t8_h_done, portMAX_DELAY );

        /* Drain Med's leftover work so it cannot starve Low next round. */
        xSemaphoreTake( t8_med_done, portMAX_DELAY );

        if( round + 1 < T8_ROUNDS )
            xSemaphoreGive( t8_next_round );
    }

#if configUSE_TRACE_FACILITY
    traceINTERVAL_STOP( 8 );
#endif

    vSemaphoreDelete( t8_mtx );
    vSemaphoreDelete( t8_lock_held );
    vSemaphoreDelete( t8_med_go );
    vSemaphoreDelete( t8_med_seen );
    vSemaphoreDelete( t8_med_done );
    vSemaphoreDelete( t8_high_go );
    vSemaphoreDelete( t8_h_done );
    vSemaphoreDelete( t8_next_round );

    if( t8_inherit_rounds != ( uint32_t )T8_ROUNDS )
    {
        printf( "  FAIL: expected %d inherit rounds, got %u\n",
                T8_ROUNDS, (unsigned)t8_inherit_rounds );
        ++fail;
    }
    if( t8_inherit_ok != 1 )
    {
        printf( "  FAIL: Low was not boosted to priority %d while holding\n",
                (int)INV_HIGH_PRIORITY );
        ++fail;
    }
    return fail;
}

/* ==================================================================
 * TEST 9 - Task suspend / resume (vTaskSuspend / vTaskResume)
 *
 * T9_SUBJECTS tasks (SR0..SRN-1), pinned across cores on SMP, each run
 * T9_ROUNDS of two patterns so BTFViewer Task Lifecycle / timeline show
 * many suspend+resume STI pairs without long busy-waits:
 *
 *   A. Suspend-while-blocked
 *      Subject signals ready and blocks on go.  Runner suspends, gives
 *      go (wait satisfied but must stay frozen), yields, then resumes.
 *
 *   B. Suspend-while-running
 *      Subject signals ready and busy-spins on a per-subject gate.
 *      Runner suspends mid-spin, checks the busy counter is frozen,
 *      opens the gate, resumes — subject exits and signals done.
 *
 * Within a round the runner suspends *all* subjects before resuming any,
 * so the trace shows overlapping suspended windows across cores.
 *
 * Correctness: t9_ok_blocked == T9_SUBJECTS*T9_ROUNDS and
 * t9_ok_running == T9_SUBJECTS*T9_ROUNDS.
 * ================================================================== */

#define T9_PHASE_BLK_WAIT   1u
#define T9_PHASE_BLK_DONE   2u
#define T9_PHASE_RUN_BUSY   3u
#define T9_PHASE_RUN_DONE   4u

typedef struct
{
    SemaphoreHandle_t     ready;
    SemaphoreHandle_t     go;
    SemaphoreHandle_t     done;
    SemaphoreHandle_t     next;
    TaskHandle_t          handle;
    volatile uint32_t     phase;
    volatile uint32_t     busy_ctr;
    volatile uint32_t     run_gate;
} t9_subj_t;

static t9_subj_t          t9_subj[ T9_SUBJECTS ];
static volatile uint32_t  t9_ok_blocked;
static volatile uint32_t  t9_ok_running;
static volatile uint32_t  t9_fillers_stop;

static BaseType_t prvT9CreateSubject( TaskFunction_t fn, const char *name,
                                      void *arg, TaskHandle_t *out,
                                      UBaseType_t core_idx )
{
#if ( configNUMBER_OF_CORES > 1 ) && ( configUSE_CORE_AFFINITY == 1 )
    UBaseType_t mask = ( UBaseType_t )( 1u << ( core_idx % configNUMBER_OF_CORES ) );
    return xTaskCreateAffinitySet( fn, name, TASK_STACK_WORDS, arg,
                                   BOOST_PRIORITY, mask, out );
#else
    (void)core_idx;
    return xTaskCreate( fn, name, TASK_STACK_WORDS, arg,
                        BOOST_PRIORITY, out );
#endif
}

static void vSuspResSubject( void *pvArg )
{
    t9_subj_t *s = &t9_subj[ ( intptr_t )pvArg ];
    int round;

    for( round = 0; round < T9_ROUNDS; ++round )
    {
        /* ---- A: block, then continue only after resume ---- */
        s->phase = T9_PHASE_BLK_WAIT;
        xSemaphoreGive( s->ready );
        xSemaphoreTake( s->go, portMAX_DELAY );
        s->phase = T9_PHASE_BLK_DONE;
        xSemaphoreGive( s->done );
        xSemaphoreTake( s->next, portMAX_DELAY );

        /* ---- B: busy-spin until runner opens run_gate after resume ---- */
        s->run_gate = 0;
        s->phase    = T9_PHASE_RUN_BUSY;
        xSemaphoreGive( s->ready );
        while( s->run_gate == 0 )
        {
            s->busy_ctr++;
            /* Occasional yield so fillers / other subjects stay schedulable
             * on single-core; on SMP the pin keeps this core hot. */
            if( ( s->busy_ctr & 0x0Fu ) == 0u )
                taskYIELD();
        }
        s->phase = T9_PHASE_RUN_DONE;
        xSemaphoreGive( s->done );

        if( round + 1 < T9_ROUNDS )
            xSemaphoreTake( s->next, portMAX_DELAY );
    }

    vTaskDelete( NULL );
}

static void vSuspResFiller( void *pvArg )
{
    (void)pvArg;

    while( t9_fillers_stop == 0 )
        taskYIELD();

    vTaskDelete( NULL );
}

static void prvT9YieldBurst( void )
{
    int i;

    for( i = 0; i < ( int )configNUMBER_OF_CORES; ++i )
        taskYIELD();
}

static int run_test9( void )
{
    int i, round, fail = 0;
    char name[ 8 ];

    t9_ok_blocked   = 0;
    t9_ok_running   = 0;
    t9_fillers_stop = 0;

    for( i = 0; i < T9_SUBJECTS; ++i )
    {
        t9_subj[ i ].phase    = 0;
        t9_subj[ i ].busy_ctr = 0;
        t9_subj[ i ].run_gate = 0;
        t9_subj[ i ].handle   = NULL;
        t9_subj[ i ].ready    = xSemaphoreCreateBinary();
        t9_subj[ i ].go       = xSemaphoreCreateBinary();
        t9_subj[ i ].done     = xSemaphoreCreateBinary();
        t9_subj[ i ].next     = xSemaphoreCreateBinary();
        configASSERT( t9_subj[ i ].ready && t9_subj[ i ].go &&
                      t9_subj[ i ].done && t9_subj[ i ].next );

        snprintf( name, sizeof( name ), "SR%d", i );
        configASSERT( prvT9CreateSubject( vSuspResSubject, name,
                                          ( void * )( intptr_t )i,
                                          &t9_subj[ i ].handle,
                                          ( UBaseType_t )i ) == pdPASS );
    }

    for( i = 0; i < T9_FILLERS; ++i )
        configASSERT( xTaskCreate( vSuspResFiller, "SF",
                                   TASK_STACK_WORDS, NULL,
                                   WORKER_PRIORITY, NULL ) == pdPASS );

#if configUSE_TRACE_FACILITY
    traceINTERVAL_START( 9 );
#endif

    for( round = 0; round < T9_ROUNDS; ++round )
    {
        /* ---- A: suspend-while-blocked (all subjects overlapping) ---- */
        for( i = 0; i < T9_SUBJECTS; ++i )
            xSemaphoreTake( t9_subj[ i ].ready, portMAX_DELAY );

        for( i = 0; i < T9_SUBJECTS; ++i )
            vTaskSuspend( t9_subj[ i ].handle );

        for( i = 0; i < T9_SUBJECTS; ++i )
            xSemaphoreGive( t9_subj[ i ].go );

        prvT9YieldBurst();

        for( i = 0; i < T9_SUBJECTS; ++i )
        {
            if( t9_subj[ i ].phase != T9_PHASE_BLK_WAIT )
            {
                printf( "  FAIL: SR%d round %d ran while suspended-blocked"
                        " (phase=%u)\n",
                        i, round, (unsigned)t9_subj[ i ].phase );
                ++fail;
            }
        }

        for( i = 0; i < T9_SUBJECTS; ++i )
            vTaskResume( t9_subj[ i ].handle );

        for( i = 0; i < T9_SUBJECTS; ++i )
        {
            xSemaphoreTake( t9_subj[ i ].done, portMAX_DELAY );
            if( t9_subj[ i ].phase != T9_PHASE_BLK_DONE )
            {
                printf( "  FAIL: SR%d round %d blocked-resume phase=%u\n",
                        i, round, (unsigned)t9_subj[ i ].phase );
                ++fail;
            }
            else
                t9_ok_blocked++;
            xSemaphoreGive( t9_subj[ i ].next );
        }

        /* ---- B: suspend-while-running (overlapping across subjects) ---- */
        for( i = 0; i < T9_SUBJECTS; ++i )
            xSemaphoreTake( t9_subj[ i ].ready, portMAX_DELAY );

        /* Let subjects enter the busy loop before suspending. */
        prvT9YieldBurst();

        {
            uint32_t snap[ T9_SUBJECTS ];

            for( i = 0; i < T9_SUBJECTS; ++i )
                vTaskSuspend( t9_subj[ i ].handle );

            /* Remote cores may still retire a few instructions after
             * vTaskSuspend returns — settle, then sample. */
            prvT9YieldBurst();
            for( i = 0; i < T9_SUBJECTS; ++i )
                snap[ i ] = t9_subj[ i ].busy_ctr;
            prvT9YieldBurst();

            for( i = 0; i < T9_SUBJECTS; ++i )
            {
                if( t9_subj[ i ].phase != T9_PHASE_RUN_BUSY )
                {
                    printf( "  FAIL: SR%d round %d not busy when suspended"
                            " (phase=%u)\n",
                            i, round, (unsigned)t9_subj[ i ].phase );
                    ++fail;
                }
                if( t9_subj[ i ].busy_ctr == 0u )
                {
                    printf( "  FAIL: SR%d round %d never ran before suspend\n",
                            i, round );
                    ++fail;
                }
                if( t9_subj[ i ].busy_ctr != snap[ i ] )
                {
                    printf( "  FAIL: SR%d round %d advanced while"
                            " suspended-running (%u -> %u)\n",
                            i, round,
                            (unsigned)snap[ i ],
                            (unsigned)t9_subj[ i ].busy_ctr );
                    ++fail;
                }
                /* Open the gate while still suspended — must not observe. */
                t9_subj[ i ].run_gate = 1;
            }

            prvT9YieldBurst();

            for( i = 0; i < T9_SUBJECTS; ++i )
            {
                if( t9_subj[ i ].phase != T9_PHASE_RUN_BUSY ||
                    t9_subj[ i ].busy_ctr != snap[ i ] )
                {
                    printf( "  FAIL: SR%d round %d ran on gated suspend"
                            " (phase=%u ctr=%u)\n",
                            i, round,
                            (unsigned)t9_subj[ i ].phase,
                            (unsigned)t9_subj[ i ].busy_ctr );
                    ++fail;
                }
            }

            /* Resume in reverse order so the STI timeline is not uniform. */
            for( i = T9_SUBJECTS - 1; i >= 0; --i )
                vTaskResume( t9_subj[ i ].handle );

            for( i = 0; i < T9_SUBJECTS; ++i )
            {
                xSemaphoreTake( t9_subj[ i ].done, portMAX_DELAY );
                if( t9_subj[ i ].phase != T9_PHASE_RUN_DONE )
                {
                    printf( "  FAIL: SR%d round %d running-resume phase=%u\n",
                            i, round, (unsigned)t9_subj[ i ].phase );
                    ++fail;
                }
                else
                    t9_ok_running++;
            }
        }

        if( round + 1 < T9_ROUNDS )
        {
            for( i = 0; i < T9_SUBJECTS; ++i )
                xSemaphoreGive( t9_subj[ i ].next );
        }
    }

#if configUSE_TRACE_FACILITY
    traceINTERVAL_STOP( 9 );
#endif

    t9_fillers_stop = 1;
    prvT9YieldBurst();
    prvT9YieldBurst();

    for( i = 0; i < T9_SUBJECTS; ++i )
    {
        vSemaphoreDelete( t9_subj[ i ].ready );
        vSemaphoreDelete( t9_subj[ i ].go );
        vSemaphoreDelete( t9_subj[ i ].done );
        vSemaphoreDelete( t9_subj[ i ].next );
    }

    {
        const uint32_t want = ( uint32_t )( T9_SUBJECTS * T9_ROUNDS );

        if( t9_ok_blocked != want )
        {
            printf( "  FAIL: blocked-suspend oks %u want %u\n",
                    (unsigned)t9_ok_blocked, (unsigned)want );
            ++fail;
        }
        if( t9_ok_running != want )
        {
            printf( "  FAIL: running-suspend oks %u want %u\n",
                    (unsigned)t9_ok_running, (unsigned)want );
            ++fail;
        }
    }
    return fail;
}

/* ==================================================================
 * TEST 10 - Core affinity (vTaskCoreAffinitySet / Get)
 *
 * Requires configUSE_CORE_AFFINITY=1 and configNUMBER_OF_CORES>1.
 * On a single-core build the test is a no-op pass.
 *
 * A. Pin — one BOOST_PRIORITY task per core (mask = 1<<core), created with
 *    xTaskCreateAffinitySet then reinforced by vTaskCoreAffinitySet(NULL)
 *    so the BTF ENTER hook records affinity_set STI.  Each task samples
 *    portGET_CORE_ID() for a short yield loop; every sample must match.
 *
 * B. Migrate — one task pinned to core 0, then re-pinned to the last core;
 *    after a few yields it must only observe the new core.
 * ================================================================== */

#if ( configNUMBER_OF_CORES > 1 ) && ( configUSE_CORE_AFFINITY == 1 )

#define T10_PIN_ITERS      ( 6 )
#define T10_MIG_ITERS      ( 4 )

static SemaphoreHandle_t  t10_done;
static volatile uint32_t  t10_pin_fail;
static volatile uint32_t  t10_get_fail;
static volatile uint32_t  t10_mig_fail;

static void vAffPinned( void *pvArg )
{
    int core = (int)(intptr_t)pvArg;
    UBaseType_t mask = ( UBaseType_t )( 1u << core );
    int i;

    /* Emit affinity STI (create-time mask is not traced by FreeRTOS V11). */
    vTaskCoreAffinitySet( NULL, mask );

    if( vTaskCoreAffinityGet( NULL ) != mask )
        t10_get_fail++;

    for( i = 0; i < T10_PIN_ITERS; ++i )
    {
        if( portGET_CORE_ID() != ( BaseType_t )core )
            t10_pin_fail++;
        taskYIELD();
    }

    xSemaphoreGive( t10_done );
    vTaskDelete( NULL );
}

static void vAffMigrate( void *pvArg )
{
    const int last = (int)configNUMBER_OF_CORES - 1;
    UBaseType_t mask0 = ( UBaseType_t )( 1u << 0 );
    UBaseType_t maskN = ( UBaseType_t )( 1u << last );
    int i;
    (void)pvArg;

    vTaskCoreAffinitySet( NULL, mask0 );
    if( vTaskCoreAffinityGet( NULL ) != mask0 )
        t10_get_fail++;

    for( i = 0; i < T10_MIG_ITERS; ++i )
    {
        if( portGET_CORE_ID() != ( BaseType_t )0 )
            t10_mig_fail++;
        taskYIELD();
    }

    vTaskCoreAffinitySet( NULL, maskN );
    if( vTaskCoreAffinityGet( NULL ) != maskN )
        t10_get_fail++;

    /* Allow the scheduler to migrate us off core 0. */
    for( i = 0; i < (int)configNUMBER_OF_CORES + 2; ++i )
        taskYIELD();

    for( i = 0; i < T10_MIG_ITERS; ++i )
    {
        if( portGET_CORE_ID() != ( BaseType_t )last )
            t10_mig_fail++;
        taskYIELD();
    }

    xSemaphoreGive( t10_done );
    vTaskDelete( NULL );
}

static int run_test10( void )
{
    int c, fail = 0;
    const int n_pin = (int)configNUMBER_OF_CORES;

    t10_pin_fail = 0;
    t10_get_fail = 0;
    t10_mig_fail = 0;
    t10_done     = xSemaphoreCreateCounting( ( UBaseType_t )( n_pin + 1 ), 0 );
    configASSERT( t10_done );

#if configUSE_TRACE_FACILITY
    traceINTERVAL_START( 10 );
#endif

    for( c = 0; c < n_pin; ++c )
    {
        UBaseType_t mask = ( UBaseType_t )( 1u << c );
        configASSERT( xTaskCreateAffinitySet(
                          vAffPinned, "Aff",
                          TASK_STACK_WORDS, (void *)(intptr_t)c,
                          BOOST_PRIORITY, mask, NULL ) == pdPASS );
    }

    configASSERT( xTaskCreate( vAffMigrate, "AffM",
                               TASK_STACK_WORDS, NULL,
                               BOOST_PRIORITY, NULL ) == pdPASS );

    for( c = 0; c < n_pin + 1; ++c )
        xSemaphoreTake( t10_done, portMAX_DELAY );

#if configUSE_TRACE_FACILITY
    traceINTERVAL_STOP( 10 );
#endif

    vSemaphoreDelete( t10_done );

    if( t10_get_fail != 0 )
    {
        printf( "  FAIL: vTaskCoreAffinityGet mismatches (%u)\n",
                (unsigned)t10_get_fail );
        ++fail;
    }
    if( t10_pin_fail != 0 )
    {
        printf( "  FAIL: pinned task ran off-mask (%u samples)\n",
                (unsigned)t10_pin_fail );
        ++fail;
    }
    if( t10_mig_fail != 0 )
    {
        printf( "  FAIL: migrate task off expected core (%u samples)\n",
                (unsigned)t10_mig_fail );
        ++fail;
    }
    return fail;
}

#else /* !SMP affinity */

static int run_test10( void )
{
    /* Core affinity APIs require configNUMBER_OF_CORES > 1. */
    return 0;
}

#endif /* configNUMBER_OF_CORES > 1 && configUSE_CORE_AFFINITY */

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
    { "10: core affinity",         run_test10 },
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
