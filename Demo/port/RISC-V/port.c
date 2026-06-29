/*
 * Demo/port/RISC-V/port.c
 *
 * Replaces FreeRTOS-Kernel/portable/GCC/RISC-V/port.c.
 * Supports both single-core (configNUMBER_OF_CORES == 1) and
 * SMP (configNUMBER_OF_CORES > 1) builds via preprocessor guards.
 *
 * Hardware (CLINT at 0x02000000):
 *   MSIP     : base + hartid * 4
 *   mtimecmp : base + 0x4000 + hartid * 8  (= configMTIMECMP_BASE_ADDRESS + …)
 *   mtime    : base + 0xBFF8               (= configMTIME_BASE_ADDRESS)
 *
 * No dependency on platform.h — CLINT access uses direct volatile pointers
 * and inline assembly.
 */

#include "FreeRTOS.h"
#include "task.h"
#include "portmacro.h"
#include <stdint.h>
#include <string.h>

/* ====================================================================
 * CLINT register access — no external header needed.
 * ==================================================================== */
#define portCLINT_BASE              ( 0x02000000UL )
#define portCLINT_MSIP_REG( hart )  \
    ( *( volatile uint32_t * )( portCLINT_BASE + 4UL * ( uint32_t )( hart ) ) )

/* ====================================================================
 * Symbols shared by both single-core and SMP paths.
 *
 * portContext.h (included by portASM.S) declares these via .extern even
 * in SMP builds.  In SMP builds they are only compatibility stubs —
 * the SMP trap handler never references them in code.
 * ==================================================================== */
#ifdef configTASK_RETURN_ADDRESS
    #define portTASK_RETURN_ADDRESS    configTASK_RETURN_ADDRESS
#else
    #define portTASK_RETURN_ADDRESS    0
#endif

size_t   xCriticalNesting   = ( size_t ) 0xaaaaaaaa;
size_t * pxCriticalNesting  = &xCriticalNesting;
size_t   xTaskReturnAddress = ( size_t ) portTASK_RETURN_ADDRESS;

extern void xPortStartFirstTask( void );

/* ====================================================================
 * SINGLE-CORE  (configNUMBER_OF_CORES == 1 or not defined)
 * ==================================================================== */
#if !defined( configNUMBER_OF_CORES ) || ( configNUMBER_OF_CORES == 1 )

/* ISR stack: use linker-symbol method (freertos_irq_stack_top defined in
 * linker.ld), or override with configISR_STACK_SIZE_WORDS.            */
#ifdef configISR_STACK_SIZE_WORDS
    static __attribute__( ( aligned( 16 ) ) )
    StackType_t xISRStack[ configISR_STACK_SIZE_WORDS ];
    const StackType_t xISRStackTop =
        ( StackType_t ) &xISRStack[
            configISR_STACK_SIZE_WORDS & ~( ( StackType_t ) portBYTE_ALIGNMENT_MASK ) ];
#else
    extern const uint32_t __freertos_irq_stack_top[];
    const StackType_t xISRStackTop = ( StackType_t ) __freertos_irq_stack_top;
#endif

/* Timer state referenced by portASM.S (portUPDATE_MTIMER_COMPARE_REGISTER). */
uint64_t        ullNextTime                          = 0ULL;
const uint64_t *pullNextTime                         = &ullNextTime;
const size_t    uxTimerIncrementsForOneTick          =
    ( size_t ) ( configCPU_CLOCK_HZ / configTICK_RATE_HZ );
UBaseType_t const ullMachineTimerCompareRegisterBase = configMTIMECMP_BASE_ADDRESS;
volatile uint64_t *pullMachineTimerCompareRegister   = NULL;

void vPortSetupTimerInterrupt( void )
{
    uint32_t           ulCurrentTimeHigh, ulCurrentTimeLow;
    volatile uint32_t *pulTimeHigh =
        ( volatile uint32_t * ) ( configMTIME_BASE_ADDRESS + 4UL );
    volatile uint32_t *pulTimeLow  =
        ( volatile uint32_t * ) configMTIME_BASE_ADDRESS;
    volatile uint32_t  ulHartId;

    __asm volatile( "csrr %0, mhartid" : "=r"( ulHartId ) );

    pullMachineTimerCompareRegister =
        ( volatile uint64_t * ) ( ullMachineTimerCompareRegisterBase +
                                  ( ulHartId * sizeof( uint64_t ) ) );

    do {
        ulCurrentTimeHigh = *pulTimeHigh;
        ulCurrentTimeLow  = *pulTimeLow;
    } while( ulCurrentTimeHigh != *pulTimeHigh );

    ullNextTime  = ( uint64_t ) ulCurrentTimeHigh;
    ullNextTime <<= 32ULL;
    ullNextTime |= ( uint64_t ) ulCurrentTimeLow;
    ullNextTime += ( uint64_t ) uxTimerIncrementsForOneTick;

    *pullMachineTimerCompareRegister = ullNextTime;
    ullNextTime += ( uint64_t ) uxTimerIncrementsForOneTick;
}

BaseType_t xPortStartScheduler( void )
{
    configASSERT( ( xISRStackTop & ( StackType_t ) portBYTE_ALIGNMENT_MASK ) == 0 );
    vPortSetupTimerInterrupt();
    /* Enable MTIE | MEIE. */
    __asm volatile( "csrs mie, %0" :: "r"( 0x880u ) : "memory" );
    xPortStartFirstTask();
    return pdFALSE; /* never reached */
}

/* ====================================================================
 * SMP  (configNUMBER_OF_CORES > 1)
 * ==================================================================== */
#else /* configNUMBER_OF_CORES > 1 */

#if ( configNUMBER_OF_CORES > 16 )
    #error "port.c: configNUMBER_OF_CORES must not exceed 16."
#endif

#define portISR_STACK_WORDS 512u

/* Per-core ISR stacks sized to the actual core count, not the maximum.
 * xISRStackTops[] is indexed by mhartid in portASM.S; each hart
 * initialises its own entry inside vPortSetupTimerInterrupt(). */
static __attribute__( ( aligned( 16 ) ) )
StackType_t xISRStacks[ configNUMBER_OF_CORES ][ portISR_STACK_WORDS ];

StackType_t xISRStackTops[ configNUMBER_OF_CORES ];

/* Per-core timer state referenced by portASM.S. */
uint64_t           ullNextTimes[ configNUMBER_OF_CORES ];
volatile uint64_t *pullMachineTimerCompareRegisters[ configNUMBER_OF_CORES ];

const size_t uxTimerIncrementsForOneTick =
    ( size_t ) ( configCPU_CLOCK_HZ / configTICK_RATE_HZ );
UBaseType_t const ullMachineTimerCompareRegisterBase = configMTIMECMP_BASE_ADDRESS;

/* ---- TTAS spinlocks ---- */

/* The ISR lock is a RECURSIVE (owner + count) spinlock, mirroring the
 * Xtensa xt_mutex design.  This allows the same core to re-acquire it
 * via taskENTER_CRITICAL_FROM_ISR() while already holding it (e.g.
 * inside vTaskSwitchContext which holds both locks before calling the
 * traceTASK_SWITCHED_OUT/IN hooks).                                   */
typedef struct
{
    volatile uint32_t owner; /* hartid + 1, or 0 when free              */
    volatile uint32_t count; /* recursion depth                         */
} ISRLock_t;

static ISRLock_t xISRLock = { 0u, 0u };

/* The task lock must be RECURSIVE (per-core reference-counted) because
 * the FreeRTOS SMP V11 kernel acquires it in two nested ways:
 *   1. vTaskSuspendAll()   → portGET_TASK_LOCK (direct, count 0→1)
 *   2. xTaskResumeAll()    → taskENTER_CRITICAL → vTaskEnterCritical
 *                            → portGET_TASK_LOCK if nesting==0 (count 1→2)
 *      then portRELEASE_TASK_LOCK inside the body (count 2→1)
 *      then taskEXIT_CRITICAL → portRELEASE_TASK_LOCK (count 1→0)
 * A plain TAS spinlock would deadlock at step 2 on the same core.
 * We implement recursion by tracking the owner core and a per-core
 * acquisition count; the underlying AMO lock is only taken/released
 * when the count transitions 0↔1.                                    */
#define portNO_OWNER  ( ( uint32_t ) 0xFFFFFFFFu )

static volatile uint32_t xTaskLockRaw   = 0u;          /* 0=free, 1=held */
static volatile uint32_t xTaskLockOwner = portNO_OWNER; /* owning hart id */
static volatile uint32_t xTaskLockDepth = 0u;           /* recursion depth */

static void prvSpinLockRaw( volatile uint32_t *pLock )
{
    uint32_t prev;
    do {
        while( *pLock != 0u )
            __asm__ volatile( "" ::: "memory" );
        __asm__ volatile(
            "amoswap.w.aqrl %0, %2, (%1)"
            : "=r"( prev )
            : "r"( pLock ), "r"( 1u )
            : "memory" );
    } while( prev != 0u );
}

static void prvSpinUnlockRaw( volatile uint32_t *pLock )
{
    __asm__ volatile( "fence rw, rw" ::: "memory" );
    *pLock = 0u;
}

void vPortGetTaskLock( void )
{
    uint32_t hartid;
    __asm__ volatile( "csrr %0, mhartid" : "=r"( hartid ) );

    if( xTaskLockOwner == hartid )
    {
        /* Same core re-acquiring: just increment depth. */
        xTaskLockDepth++;
        __asm__ volatile( "" ::: "memory" );
    }
    else
    {
        /* Different core (or first acquisition): spin on raw lock. */
        prvSpinLockRaw( &xTaskLockRaw );
        xTaskLockOwner = hartid;
        xTaskLockDepth = 1u;
    }
}

void vPortReleaseTaskLock( void )
{
    if( xTaskLockDepth > 1u )
    {
        xTaskLockDepth--;
        __asm__ volatile( "" ::: "memory" );
    }
    else
    {
        xTaskLockOwner = portNO_OWNER;
        xTaskLockDepth = 0u;
        prvSpinUnlockRaw( &xTaskLockRaw );
    }
}

void vPortGetISRLock( void )
{
    uint32_t hartid;
    __asm__ volatile( "csrr %0, mhartid" : "=r"( hartid ) );
    uint32_t id = hartid + 1u; /* 0 is reserved for "free" */

    if( xISRLock.owner == id )
    {
        /* Same core re-acquiring: just increment depth. */
        xISRLock.count++;
        __asm__ volatile( "" ::: "memory" );
    }
    else
    {
        /* Spin until the lock is free, then claim it with an AMO. */
        uint32_t prev;
        do {
            while( xISRLock.owner != 0u )
                __asm__ volatile( "" ::: "memory" );
            __asm__ volatile(
                "amoswap.w.aqrl %0, %2, (%1)"
                : "=r"( prev )
                : "r"( &xISRLock.owner ), "r"( id )
                : "memory" );
        } while( prev != 0u );
        xISRLock.count = 1u;
    }
}

void vPortReleaseISRLock( void )
{
    uint32_t hartid;
    __asm__ volatile( "csrr %0, mhartid" : "=r"( hartid ) );

    if( xISRLock.owner == ( hartid + 1u ) )
    {
        if( xISRLock.count > 1u )
        {
            xISRLock.count--;
            __asm__ volatile( "" ::: "memory" );
        }
        else
        {
            xISRLock.count = 0u;
            __asm__ volatile( "fence rw, rw" ::: "memory" );
            xISRLock.owner = 0u;
        }
    }
}

/* ---- xPortTimerTickHandler -------------------------------------------
 * Called from the SMP timer ISR (portASM.S) instead of calling
 * xTaskIncrementTick() directly.
 *
 * FreeRTOS SMP V11 requires xTaskIncrementTick() to be called while:
 *   (a) the task lock is held  — protects ready/delayed lists
 *   (b) the ISR lock is held   — held by vTaskEnterCriticalFromISR
 *   (c) critical nesting > 0   — asserted by prvYieldForTask()
 *
 * Calling xTaskIncrementTick() raw from assembly violates (b) and (c),
 * causing a configASSERT spin when a delayed task's timeout expires.
 * -------------------------------------------------------------------- */
BaseType_t xPortTimerTickHandler( void )
{
    UBaseType_t uxSavedInterruptStatus;
    BaseType_t  xSwitchRequired;

    /* Lock ordering: task lock first, then ISR lock (via FromISR call). */
    vPortGetTaskLock();
    uxSavedInterruptStatus = vTaskEnterCriticalFromISR(); /* ISR lock + nesting++ */

    xSwitchRequired = xTaskIncrementTick();

    vTaskExitCriticalFromISR( uxSavedInterruptStatus );   /* ISR lock + nesting-- */
    vPortReleaseTaskLock();

    return xSwitchRequired;
}

/* ---- portYIELD_CORE: assert MSIP on target hart ---- */
void vPortYieldCore( BaseType_t xCoreID )
{
    portCLINT_MSIP_REG( xCoreID ) = 1u;
}

/* ---- Per-core timer setup ---- */
void vPortSetupTimerInterrupt( void )
{
    uint32_t           ulCurrentTimeHigh, ulCurrentTimeLow;
    volatile uint32_t *pulTimeHigh =
        ( volatile uint32_t * ) ( configMTIME_BASE_ADDRESS + 4UL );
    volatile uint32_t *pulTimeLow  =
        ( volatile uint32_t * ) configMTIME_BASE_ADDRESS;
    volatile uint32_t  ulHartId;

    __asm volatile( "csrr %0, mhartid" : "=r"( ulHartId ) );

    xISRStackTops[ ulHartId ] =
        ( StackType_t ) &xISRStacks[ ulHartId ][
            portISR_STACK_WORDS & ~( ( size_t ) portBYTE_ALIGNMENT_MASK ) ];

    pullMachineTimerCompareRegisters[ ulHartId ] =
        ( volatile uint64_t * ) ( ullMachineTimerCompareRegisterBase +
                                  ( ulHartId * sizeof( uint64_t ) ) );

    if( ulHartId == 0U )
    {
        /* Hart 0 owns the FreeRTOS tick: local MTIP drives xTaskIncrementTick.
         * Other cores are synchronised via MSIP (portYIELD_CORE) from the kernel. */
        do {
            ulCurrentTimeHigh = *pulTimeHigh;
            ulCurrentTimeLow  = *pulTimeLow;
        } while( ulCurrentTimeHigh != *pulTimeHigh );

        ullNextTimes[ 0 ]  = ( uint64_t ) ulCurrentTimeHigh;
        ullNextTimes[ 0 ] <<= 32ULL;
        ullNextTimes[ 0 ] |= ( uint64_t ) ulCurrentTimeLow;
        ullNextTimes[ 0 ] += ( uint64_t ) uxTimerIncrementsForOneTick;

        *pullMachineTimerCompareRegisters[ 0 ] = ullNextTimes[ 0 ];
        ullNextTimes[ 0 ] += ( uint64_t ) uxTimerIncrementsForOneTick;

        /* MTIE | MSIE | MEIE */
        __asm volatile( "csrs mie, %0" :: "r"( 0x888u ) : "memory" );
    }
    else
    {
        /* Secondary harts: no local tick timer — only IPI (MSIP) and external IRQs. */
        *pullMachineTimerCompareRegisters[ ulHartId ] = UINT64_MAX;

        /* MSIE | MEIE (no MTIE). */
        __asm volatile( "csrs mie, %0" :: "r"( 0x808u ) : "memory" );
    }
}

/* ---- xPortStartScheduler (called only from hart 0) ---- */
BaseType_t xPortStartScheduler( void )
{
    configASSERT( ( xISRStackTops[ 0 ] & ( StackType_t ) portBYTE_ALIGNMENT_MASK ) == 0 );
    vPortSetupTimerInterrupt();
    xPortStartFirstTask();
    return pdFALSE; /* never reached */
}

/* ---- vPortSecondaryHartEntry (called by harts 1..N-1 from crt0.S) ---- */
void vPortSecondaryHartEntry( void )
{
    extern void freertos_risc_v_trap_handler( void );
    extern void * volatile pxCurrentTCBs[ configNUMBER_OF_CORES ];
    volatile uint32_t ulHartId;

    __asm volatile( "csrr %0, mhartid" : "=r"( ulHartId ) );

    /* Install trap handler (was previously done in main() before this call). */
    __asm volatile( "csrw mtvec, %0" : : "r"( freertos_risc_v_trap_handler ) : "memory" );

    /* Wait until hart 0 has started the scheduler and populated our TCB slot. */
    while( xTaskGetSchedulerState() == taskSCHEDULER_NOT_STARTED )
    {
        __asm volatile( "" ::: "memory" );
    }
    while( pxCurrentTCBs[ ulHartId ] == NULL )
    {
        __asm volatile( "" ::: "memory" );
    }

    vPortSetupTimerInterrupt();
    xPortStartFirstTask();
    /* never reached */
}

#endif /* configNUMBER_OF_CORES */
