/*
 * portmacro.h — standalone platform header for the FreeRTOS RISC-V GCC port.
 *
 * Self-contained: does NOT depend on FreeRTOS-Kernel/portable/GCC/RISC-V/.
 * All type definitions and architecture macros are defined directly here.
 *
 * Supports both configurations via the configNUMBER_OF_CORES constant:
 *
 *   configNUMBER_OF_CORES == 1 (or undefined)  →  SINGLE-CORE path
 *     • portGET_CORE_ID() always returns 0.
 *     • portYIELD_CORE(x) maps to portYIELD().
 *     • portCRITICAL_NESTING_IN_TCB = 0  (global xCriticalNesting).
 *
 *   configNUMBER_OF_CORES > 1                  →  SMP path
 *     • portGET_CORE_ID() reads mhartid CSR.
 *     • portYIELD_CORE(x) asserts the target hart's CLINT MSIP bit.
 *     • portCRITICAL_NESTING_IN_TCB = 1  (count stored in TCB).
 *     • Per-core critical-section/spinlock macros for SMP tasks.c.
 */

#ifndef __PORTMACRO_H
#define __PORTMACRO_H

/* *INDENT-OFF* */
#ifdef __cplusplus
    extern "C" {
#endif
/* *INDENT-ON* */

/* ================================================================
 * Type definitions (RV64 / RV32)
 * ================================================================ */
#if __riscv_xlen == 64
    #define portSTACK_TYPE           uint64_t
    #define portBASE_TYPE            int64_t
    #define portUBASE_TYPE           uint64_t
    #define portMAX_DELAY            ( TickType_t ) 0xffffffffffffffffUL
    #define portPOINTER_SIZE_TYPE    uint64_t
#elif __riscv_xlen == 32
    #define portSTACK_TYPE           uint32_t
    #define portBASE_TYPE            int32_t
    #define portUBASE_TYPE           uint32_t
    #define portMAX_DELAY            ( TickType_t ) 0xffffffffUL
#else
    #error "Assembler did not define __riscv_xlen"
#endif

typedef portSTACK_TYPE   StackType_t;
typedef portBASE_TYPE    BaseType_t;
typedef portUBASE_TYPE   UBaseType_t;
typedef portUBASE_TYPE   TickType_t;

/* Legacy type definitions. */
#define portCHAR      char
#define portFLOAT     float
#define portDOUBLE    double
#define portLONG      long
#define portSHORT     short

/* 32/64-bit tick type: reads are atomic on this platform. */
#define portTICK_TYPE_IS_ATOMIC    1

/* ================================================================
 * Architecture specifics
 * ================================================================ */
#define portSTACK_GROWTH      ( -1 )
#define portTICK_PERIOD_MS    ( ( TickType_t ) 1000 / configTICK_RATE_HZ )
#ifdef __riscv_32e
    #define portBYTE_ALIGNMENT    8
#else
    #define portBYTE_ALIGNMENT    16
#endif

/* ================================================================
 * Misc
 * ================================================================ */
#define portNOP()              __asm volatile ( " nop " )
#define portINLINE             __inline
#ifndef portFORCE_INLINE
    #define portFORCE_INLINE   inline __attribute__( ( always_inline ) )
#endif
#define portMEMORY_BARRIER()   __asm volatile ( "" ::: "memory" )

/* ================================================================
 * Architecture-specific optimised task selection
 * ================================================================ */
#ifndef configUSE_PORT_OPTIMISED_TASK_SELECTION
    #define configUSE_PORT_OPTIMISED_TASK_SELECTION    1
#endif

#if ( configUSE_PORT_OPTIMISED_TASK_SELECTION == 1 )
    #if ( configMAX_PRIORITIES > 32 )
        #error "configUSE_PORT_OPTIMISED_TASK_SELECTION requires configMAX_PRIORITIES <= 32."
    #endif
    #define portRECORD_READY_PRIORITY( uxPriority, uxReadyPriorities ) \
        ( uxReadyPriorities ) |= ( 1UL << ( uxPriority ) )
    #define portRESET_READY_PRIORITY( uxPriority, uxReadyPriorities ) \
        ( uxReadyPriorities ) &= ~( 1UL << ( uxPriority ) )
    #define portGET_HIGHEST_PRIORITY( uxTopPriority, uxReadyPriorities ) \
        uxTopPriority = ( 31UL - __builtin_clz( uxReadyPriorities ) )
#endif /* configUSE_PORT_OPTIMISED_TASK_SELECTION */

/* ================================================================
 * Task function macros
 * ================================================================ */
#define portTASK_FUNCTION_PROTO( vFunction, pvParameters )    void vFunction( void * pvParameters )
#define portTASK_FUNCTION( vFunction, pvParameters )          void vFunction( void * pvParameters )

/* ================================================================
 * Interrupt control
 * ================================================================ */
#define portDISABLE_INTERRUPTS()    __asm volatile ( "csrc mstatus, 8" ::: "memory" )
#define portENABLE_INTERRUPTS()     __asm volatile ( "csrs mstatus, 8" ::: "memory" )

/* ================================================================
 * Yield (ecall triggers the M-mode trap handler in portASM.S)
 * ================================================================ */
#define portYIELD()    __asm volatile ( "ecall" )

/* ================================================================
 * CLINT / MTIME — optional legacy configCLINT_BASE_ADDRESS override,
 * then chip defaults from freertos_risc_v_chip_specific_extensions.h.
 * ================================================================ */
#if defined( configCLINT_BASE_ADDRESS ) && !defined( configMTIME_BASE_ADDRESS ) && ( configCLINT_BASE_ADDRESS == 0 )
    #define configMTIME_BASE_ADDRESS       ( 0 )
    #define configMTIMECMP_BASE_ADDRESS    ( 0 )
#elif defined( configCLINT_BASE_ADDRESS ) && !defined( configMTIME_BASE_ADDRESS )
    #define configMTIME_BASE_ADDRESS       ( ( configCLINT_BASE_ADDRESS ) + 0xBFF8UL )
    #define configMTIMECMP_BASE_ADDRESS    ( ( configCLINT_BASE_ADDRESS ) + 0x4000UL )
#endif

#include "freertos_risc_v_chip_specific_extensions.h"

#if !defined( configMTIME_BASE_ADDRESS ) || !defined( configMTIMECMP_BASE_ADDRESS )
    #error "configMTIME_BASE_ADDRESS and configMTIMECMP_BASE_ADDRESS must be defined in freertos_risc_v_chip_specific_extensions.h."
#endif

/* ================================================================
 * SINGLE-CORE  (configNUMBER_OF_CORES == 1 or undefined)
 * ================================================================ */
#if !defined( configNUMBER_OF_CORES ) || ( configNUMBER_OF_CORES == 1 )

extern void vTaskSwitchContext( void );

#define portEND_SWITCHING_ISR( xSwitchRequired )         \
    do                                                    \
    {                                                     \
        if( xSwitchRequired != pdFALSE )                  \
        {                                                 \
            traceISR_EXIT_TO_SCHEDULER();                 \
            vTaskSwitchContext();                         \
        }                                                 \
        else                                              \
        {                                                 \
            traceISR_EXIT();                              \
        }                                                 \
    } while( 0 )
#define portYIELD_FROM_ISR( x )    portEND_SWITCHING_ISR( x )

/* Critical sections: global nesting counter (portCRITICAL_NESTING_IN_TCB=0). */
#define portCRITICAL_NESTING_IN_TCB    0

extern size_t xCriticalNesting;

#define portENTER_CRITICAL()                \
    do                                      \
    {                                       \
        portDISABLE_INTERRUPTS();           \
        xCriticalNesting++;                 \
    } while( 0 )

#define portEXIT_CRITICAL()                 \
    do                                      \
    {                                       \
        xCriticalNesting--;                 \
        if( xCriticalNesting == 0 )         \
        {                                   \
            portENABLE_INTERRUPTS();        \
        }                                   \
    } while( 0 )

/* portGET_CORE_ID / portYIELD_CORE stubs (uniform API with SMP builds). */
#define portGET_CORE_ID()       ( ( BaseType_t ) 0 )
#define portYIELD_CORE( x )     portYIELD()

#endif /* single-core */

/* ================================================================
 * SMP  (configNUMBER_OF_CORES > 1)
 * ================================================================ */
#if defined( configNUMBER_OF_CORES ) && ( configNUMBER_OF_CORES > 1 )

/* ------------------------------------------------------------------
 * portGET_CORE_ID(): return the current hart's 0-based core ID
 * by reading the mhartid CSR.
 * ------------------------------------------------------------------ */
static __inline__ __attribute__( ( always_inline ) )
BaseType_t xPortGetCoreID( void )
{
    BaseType_t x;
    __asm__ volatile( "csrr %0, mhartid" : "=r"( x ) );
    return x;
}
#define portGET_CORE_ID()    xPortGetCoreID()

/* ------------------------------------------------------------------
 * portYIELD_CORE(xCoreID): request a context switch on another hart
 * by asserting its CLINT MSIP bit.
 * ------------------------------------------------------------------ */
void vPortYieldCore( BaseType_t xCoreID );
#define portYIELD_CORE( x )    vPortYieldCore( x )

/* ------------------------------------------------------------------
 * portEND_SWITCHING_ISR / portYIELD_FROM_ISR
 * Calls the SMP vTaskSwitchContext(xCoreID) variant.
 * The trap handler in portASM.S drives the actual context switch;
 * this macro is for C-level ISRs that need to request a yield.
 * ------------------------------------------------------------------ */
void vTaskSwitchContext( BaseType_t xCoreID );

#define portEND_SWITCHING_ISR( xSwitchRequired )         \
    do                                                    \
    {                                                     \
        if( xSwitchRequired != pdFALSE )                  \
        {                                                 \
            traceISR_EXIT_TO_SCHEDULER();                 \
            vTaskSwitchContext( portGET_CORE_ID() );      \
        }                                                 \
        else                                              \
        {                                                 \
            traceISR_EXIT();                              \
        }                                                 \
    } while( 0 )
#define portYIELD_FROM_ISR( x )    portEND_SWITCHING_ISR( x )

/* ------------------------------------------------------------------
 * portSET_INTERRUPT_MASK / portCLEAR_INTERRUPT_MASK
 * Used by the SMP kernel to save/restore interrupt state atomically.
 * portSET_INTERRUPT_MASK returns the prior MIE bit value.
 * ------------------------------------------------------------------ */
static __inline__ __attribute__( ( always_inline ) )
UBaseType_t xPortSetInterruptMask( void )
{
    UBaseType_t prev;

    /* Atomically read mstatus and clear MIE (bit 3). */
    __asm__ volatile(
        "csrrci %0, mstatus, 8"
        : "=r"( prev )
        :
        : "memory" );
    return prev & 8u; /* return just the saved MIE bit */
}

static __inline__ __attribute__( ( always_inline ) )
void vPortClearInterruptMask( UBaseType_t uxSavedState )
{
    if( uxSavedState != 0u )
    {
        __asm__ volatile( "csrs mstatus, 8" ::: "memory" );
    }
}

#define portSET_INTERRUPT_MASK()           xPortSetInterruptMask()
#define portCLEAR_INTERRUPT_MASK( x )      vPortClearInterruptMask( x )

/* ------------------------------------------------------------------
 * Scheduler spinlocks.
 * FreeRTOS SMP uses two spinlocks:
 *   task lock  — protects the scheduler ready lists
 *   ISR lock   — protects the tick/context-switch path from ISRs
 * ------------------------------------------------------------------ */
void vPortGetTaskLock( void );
void vPortReleaseTaskLock( void );
void vPortGetISRLock( void );
void vPortReleaseISRLock( void );

#define portGET_TASK_LOCK( xCoreID )        vPortGetTaskLock()
#define portRELEASE_TASK_LOCK( xCoreID )    vPortReleaseTaskLock()
#define portGET_ISR_LOCK( xCoreID )         vPortGetISRLock()
#define portRELEASE_ISR_LOCK( xCoreID )     vPortReleaseISRLock()

/* ------------------------------------------------------------------
 * Critical sections from ISR context.
 * FreeRTOS SMP V11 calls these when entering/exiting critical
 * sections that may be taken from an ISR.
 * We delegate to tasks.c's vTaskEnterCriticalFromISR /
 * vTaskExitCriticalFromISR which handle spinlocks + nesting.
 * ------------------------------------------------------------------ */

/* Forward declarations (avoids pulling in task.h here). */
UBaseType_t vTaskEnterCriticalFromISR( void );
void        vTaskExitCriticalFromISR( UBaseType_t uxSavedInterruptStatus );

#define portENTER_CRITICAL_FROM_ISR()      vTaskEnterCriticalFromISR()
#define portEXIT_CRITICAL_FROM_ISR( x )    vTaskExitCriticalFromISR( x )

/* ------------------------------------------------------------------
 * portCRITICAL_NESTING_IN_TCB = 1 for SMP.
 * FreeRTOS SMP V11 requires nesting to be stored in the TCB so the
 * count migrates with the task when it moves between cores.
 * ------------------------------------------------------------------ */
#define portCRITICAL_NESTING_IN_TCB    1

/* ------------------------------------------------------------------
 * portENTER_CRITICAL / portEXIT_CRITICAL — SMP-aware via tasks.c.
 * ------------------------------------------------------------------ */
void vTaskEnterCritical( void );
void vTaskExitCritical( void );

#define portENTER_CRITICAL()    vTaskEnterCritical()
#define portEXIT_CRITICAL()     vTaskExitCritical()

/* ------------------------------------------------------------------
 * Secondary hart startup hook.
 * Called by non-zero harts from main() instead of parking.
 * ------------------------------------------------------------------ */
void vPortSecondaryHartEntry( void );

#endif /* configNUMBER_OF_CORES > 1 */

/* *INDENT-OFF* */
#ifdef __cplusplus
    }
#endif
/* *INDENT-ON* */

#endif /* __PORTMACRO_H */
