/*
 * Demo/port/RISC-V/portASM.S
 *
 * Merged FreeRTOS RISC-V assembly port.
 *   configNUMBER_OF_CORES == 1  →  single-core path using portContext.h macros
 *   configNUMBER_OF_CORES  > 1  →  SMP path with per-core context arrays
 *
 * Replaces FreeRTOS-Kernel/portable/GCC/RISC-V/portASM.S.
 * The FreeRTOS-Kernel submodule is NOT modified.
 */

/* Chip-specific: portasmHAS_MTIME, portasmHAS_SIFIVE_CLINT,
 * portasmADDITIONAL_CONTEXT_SIZE, portasmSAVE/RESTORE macros.         */
#include "freertos_risc_v_chip_specific_extensions.h"

/* Validate deprecated/missing chip-extension defines. */
#if defined( portasmHAS_CLINT ) && defined( portasmHAS_MTIME )
    #error The portasmHAS_CLINT constant has been deprecated. Please replace it with portasmHAS_MTIME. portasmHAS_CLINT and portasmHAS_MTIME cannot both be defined at once.
#endif
#ifdef portasmHAS_CLINT
    #warning The portasmHAS_CLINT constant has been deprecated. Please replace it with portasmHAS_MTIME and portasmHAS_SIFIVE_CLINT.
    #define portasmHAS_MTIME        portasmHAS_CLINT
    #define portasmHAS_SIFIVE_CLINT portasmHAS_CLINT
#endif
#ifndef portasmHAS_MTIME
    #error freertos_risc_v_chip_specific_extensions.h must define portasmHAS_MTIME to either 1 or 0.
#endif
#ifndef portasmHAS_SIFIVE_CLINT
    #define portasmHAS_SIFIVE_CLINT 0
#endif

/*
 * portContext.h (upstream, unmodified) provides:
 *   portWORD_SIZE, store_x, load_x, portCONTEXT_SIZE,
 *   portCRITICAL_NESTING_OFFSET, and the single-core
 *   portcontextSAVE_CONTEXT_INTERNAL / portcontextRESTORE_CONTEXT macros.
 *
 * It also emits .extern for single-core globals (pxCurrentTCB, xISRStackTop,
 * xCriticalNesting, pxCriticalNesting).  In GAS, .extern is a no-op — it
 * never generates a relocation unless the symbol is actually used in an
 * instruction.  The SMP path never expands those single-core macros, so no
 * link-time reference to those symbols is created in SMP builds.
 */
#include "portContext.h"

/* log2(portWORD_SIZE) — used by SMP path to index per-hart arrays. */
#if __riscv_xlen == 64
    #define portWORD_SIZE_LOG2   3
#else
    #define portWORD_SIZE_LOG2   2
#endif

/* CLINT MSIP base used by the SMP IPI-clear sequence. */
#define portCLINT_MSIP_BASE   0x02000000

/* ================================================================
 * Common globals
 * ================================================================ */
.global xPortStartFirstTask
.global pxPortInitialiseStack
.global freertos_risc_v_trap_handler

.weak  freertos_risc_v_application_exception_handler
.weak  freertos_risc_v_application_interrupt_handler
.extern xTaskReturnAddress

/* ================================================================
 * pxPortInitialiseStack — identical for single-core and SMP.
 *
 * Prototype (standard RISC-V ABI):
 *   StackType_t *pxPortInitialiseStack(
 *       StackType_t    *pxTopOfStack,  // a0
 *       TaskFunction_t  pxCode,        // a1
 *       void           *pvParameters); // a2
 * Returns new top-of-stack in a0.
 * ================================================================ */
.section .text.pxPortInitialiseStack
pxPortInitialiseStack:
    addi    a0, a0, -portWORD_SIZE
    store_x x0, 0(a0)              /* critical nesting slot = 0 */

#ifdef __riscv_32e
    addi    a0, a0, -(6 * portWORD_SIZE)
#else
    addi    a0, a0, -(22 * portWORD_SIZE)
#endif
    store_x a2, 0(a0)              /* a0 slot ← pvParameters */

    addi    a0, a0, -(6 * portWORD_SIZE)
    load_x  t0, xTaskReturnAddress
    store_x t0, 0(a0)              /* ra slot ← return address */

    /* Build initial mstatus: MIE=0, MPIE=1, MPP=M-mode (0x1880). */
    csrr    t0, mstatus
    andi    t0, t0, ~0x8
    addi    t1, x0, 0x188
    slli    t1, t1, 4
    or      t0, t0, t1
    addi    a0, a0, -portWORD_SIZE
    store_x t0, 0(a0)              /* mstatus slot */

    /* Chip-specific additional registers (count = portasmADDITIONAL_CONTEXT_SIZE;
     * for this platform it is 0, so the loop body never executes).    */
    addi    t0, x0, portasmADDITIONAL_CONTEXT_SIZE
.Lchip_init:
    beq     t0, x0, 1f
    addi    a0, a0, -portWORD_SIZE
    store_x x0, 0(a0)
    addi    t0, t0, -1
    j       .Lchip_init
1:
    addi    a0, a0, -portWORD_SIZE
    store_x a1, 0(a0)              /* mepc slot ← task entry (pxCode) */
    ret

/* ================================================================
 * Weak default handlers — spin so a debugger can catch them.
 * ================================================================ */
freertos_risc_v_application_exception_handler:
    csrr    t0, mcause
    csrr    t1, mepc
    csrr    t2, mstatus
    j       .

freertos_risc_v_application_interrupt_handler:
    csrr    t0, mcause
    csrr    t1, mepc
    csrr    t2, mstatus
    j       .

/* ================================================================
 * SMP PATH  (configNUMBER_OF_CORES > 1)
 * ================================================================ */
#if defined( configNUMBER_OF_CORES ) && ( configNUMBER_OF_CORES > 1 )

.extern vTaskSwitchContext
.extern xTaskIncrementTick
.extern xPortTimerTickHandler
.extern pxCurrentTCBs
.extern xISRStackTops
.extern pullMachineTimerCompareRegisters
.extern ullNextTimes
.extern uxTimerIncrementsForOneTick

/* ----------------------------------------------------------------
 * portSMPupdateMtimerCompareRegister
 * Updates this core's mtimecmp and advances ullNextTimes[hartid].
 * Clobbers: t0, t1, t2, t3, t4.
 * ---------------------------------------------------------------- */
.macro portSMPupdateMtimerCompareRegister
    csrr    t0, mhartid
    slli    t1, t0, portWORD_SIZE_LOG2
    la      t2, pullMachineTimerCompareRegisters
    add     t2, t2, t1
    load_x  t2, 0(t2)                  /* t2 = &mtimecmp[hartid] */
    slli    t1, t0, 3                  /* hartid * 8 (uint64_t stride) */
    la      t3, ullNextTimes
    add     t3, t3, t1
    ld      t4, 0(t3)                  /* t4 = ullNextTimes[hartid] */
    sd      t4, 0(t2)                  /* write mtimecmp */
    load_x  t0, uxTimerIncrementsForOneTick
    add     t4, t4, t0
    sd      t4, 0(t3)                  /* advance ullNextTimes[hartid] */
    .endm

/* ----------------------------------------------------------------
 * portSMPsaveContextInternal
 * Saves the full register context to the CURRENT task's stack.
 * sp stays on the task stack after this macro.
 * The caller must store mepc into slot 0 then switch sp to ISR stack.
 * Clobbers: t0, t1, t2 (original values already on stack).
 * ---------------------------------------------------------------- */
.macro portSMPsaveContextInternal
    addi    sp, sp, -portCONTEXT_SIZE
    store_x x1,   2 * portWORD_SIZE( sp )
    store_x x5,   3 * portWORD_SIZE( sp )
    store_x x6,   4 * portWORD_SIZE( sp )
    store_x x7,   5 * portWORD_SIZE( sp )
    store_x x8,   6 * portWORD_SIZE( sp )
    store_x x9,   7 * portWORD_SIZE( sp )
    store_x x10,  8 * portWORD_SIZE( sp )
    store_x x11,  9 * portWORD_SIZE( sp )
    store_x x12, 10 * portWORD_SIZE( sp )
    store_x x13, 11 * portWORD_SIZE( sp )
    store_x x14, 12 * portWORD_SIZE( sp )
    store_x x15, 13 * portWORD_SIZE( sp )
#ifndef __riscv_32e
    store_x x16, 14 * portWORD_SIZE( sp )
    store_x x17, 15 * portWORD_SIZE( sp )
    store_x x18, 16 * portWORD_SIZE( sp )
    store_x x19, 17 * portWORD_SIZE( sp )
    store_x x20, 18 * portWORD_SIZE( sp )
    store_x x21, 19 * portWORD_SIZE( sp )
    store_x x22, 20 * portWORD_SIZE( sp )
    store_x x23, 21 * portWORD_SIZE( sp )
    store_x x24, 22 * portWORD_SIZE( sp )
    store_x x25, 23 * portWORD_SIZE( sp )
    store_x x26, 24 * portWORD_SIZE( sp )
    store_x x27, 25 * portWORD_SIZE( sp )
    store_x x28, 26 * portWORD_SIZE( sp )
    store_x x29, 27 * portWORD_SIZE( sp )
    store_x x30, 28 * portWORD_SIZE( sp )
    store_x x31, 29 * portWORD_SIZE( sp )
#endif
    /* portCRITICAL_NESTING_IN_TCB=1: nesting count lives in TCB; store 0. */
    store_x x0, portCRITICAL_NESTING_OFFSET * portWORD_SIZE( sp )

    csrr    t0, mstatus
    store_x t0, 1 * portWORD_SIZE( sp )

    portasmSAVE_ADDITIONAL_REGISTERS       /* no-op for this platform */

    /* pxCurrentTCBs[hartid]->pxTopOfStack = sp */
    csrr    t0, mhartid
    slli    t1, t0, portWORD_SIZE_LOG2
    la      t2, pxCurrentTCBs
    add     t2, t2, t1
    load_x  t0, 0(t2)
    store_x sp, 0(t0)
    .endm

/* ----------------------------------------------------------------
 * portSMPrestoreContext
 * Loads sp from pxCurrentTCBs[hartid], restores all registers, mret.
 * ---------------------------------------------------------------- */
.macro portSMPrestoreContext
    csrr    t0, mhartid
    slli    t1, t0, portWORD_SIZE_LOG2
    la      t2, pxCurrentTCBs
    add     t2, t2, t1
    load_x  t1, 0(t2)
    load_x  sp, 0(t1)

    load_x  t0, 0(sp)
    csrw    mepc, t0

    portasmRESTORE_ADDITIONAL_REGISTERS

    /* Use t3 (not t0) so it survives any FPU/VPU restore macros. */
    load_x  t3, 1 * portWORD_SIZE( sp )
    csrw    mstatus, t3

    load_x  x1,   2 * portWORD_SIZE( sp )
    load_x  x5,   3 * portWORD_SIZE( sp )
    load_x  x6,   4 * portWORD_SIZE( sp )
    load_x  x7,   5 * portWORD_SIZE( sp )
    load_x  x8,   6 * portWORD_SIZE( sp )
    load_x  x9,   7 * portWORD_SIZE( sp )
    load_x  x10,  8 * portWORD_SIZE( sp )
    load_x  x11,  9 * portWORD_SIZE( sp )
    load_x  x12, 10 * portWORD_SIZE( sp )
    load_x  x13, 11 * portWORD_SIZE( sp )
    load_x  x14, 12 * portWORD_SIZE( sp )
    load_x  x15, 13 * portWORD_SIZE( sp )
#ifndef __riscv_32e
    load_x  x16, 14 * portWORD_SIZE( sp )
    load_x  x17, 15 * portWORD_SIZE( sp )
    load_x  x18, 16 * portWORD_SIZE( sp )
    load_x  x19, 17 * portWORD_SIZE( sp )
    load_x  x20, 18 * portWORD_SIZE( sp )
    load_x  x21, 19 * portWORD_SIZE( sp )
    load_x  x22, 20 * portWORD_SIZE( sp )
    load_x  x23, 21 * portWORD_SIZE( sp )
    load_x  x24, 22 * portWORD_SIZE( sp )
    load_x  x25, 23 * portWORD_SIZE( sp )
    load_x  x26, 24 * portWORD_SIZE( sp )
    load_x  x27, 25 * portWORD_SIZE( sp )
    load_x  x28, 26 * portWORD_SIZE( sp )
    load_x  x29, 27 * portWORD_SIZE( sp )
    load_x  x30, 28 * portWORD_SIZE( sp )
    load_x  x31, 29 * portWORD_SIZE( sp )
#endif
    addi    sp, sp, portCONTEXT_SIZE
    mret
    .endm

/* ----------------------------------------------------------------
 * xPortStartFirstTask  (SMP)
 * Loads context from pxCurrentTCBs[mhartid] and mret-enters the task.
 * ---------------------------------------------------------------- */
.section .text.xPortStartFirstTask
xPortStartFirstTask:
    csrr    t0, mhartid
    slli    t1, t0, portWORD_SIZE_LOG2
    la      t2, pxCurrentTCBs
    add     t2, t2, t1
    load_x  sp, 0(t2)
    load_x  sp, 0(sp)

    load_x  t0, 0(sp)
    csrw    mepc, t0

    portasmRESTORE_ADDITIONAL_REGISTERS

    load_x  t0, 1 * portWORD_SIZE( sp )
    csrw    mstatus, t0          /* MPIE=1, MPP=M → mret enables interrupts */

    load_x  x1,   2 * portWORD_SIZE( sp )
    load_x  x5,   3 * portWORD_SIZE( sp )
    load_x  x6,   4 * portWORD_SIZE( sp )
    load_x  x7,   5 * portWORD_SIZE( sp )
    load_x  x8,   6 * portWORD_SIZE( sp )
    load_x  x9,   7 * portWORD_SIZE( sp )
    load_x  x10,  8 * portWORD_SIZE( sp )
    load_x  x11,  9 * portWORD_SIZE( sp )
    load_x  x12, 10 * portWORD_SIZE( sp )
    load_x  x13, 11 * portWORD_SIZE( sp )
    load_x  x14, 12 * portWORD_SIZE( sp )
    load_x  x15, 13 * portWORD_SIZE( sp )
#ifndef __riscv_32e
    load_x  x16, 14 * portWORD_SIZE( sp )
    load_x  x17, 15 * portWORD_SIZE( sp )
    load_x  x18, 16 * portWORD_SIZE( sp )
    load_x  x19, 17 * portWORD_SIZE( sp )
    load_x  x20, 18 * portWORD_SIZE( sp )
    load_x  x21, 19 * portWORD_SIZE( sp )
    load_x  x22, 20 * portWORD_SIZE( sp )
    load_x  x23, 21 * portWORD_SIZE( sp )
    load_x  x24, 22 * portWORD_SIZE( sp )
    load_x  x25, 23 * portWORD_SIZE( sp )
    load_x  x26, 24 * portWORD_SIZE( sp )
    load_x  x27, 25 * portWORD_SIZE( sp )
    load_x  x28, 26 * portWORD_SIZE( sp )
    load_x  x29, 27 * portWORD_SIZE( sp )
    load_x  x30, 28 * portWORD_SIZE( sp )
    load_x  x31, 29 * portWORD_SIZE( sp )
#endif
    addi    sp, sp, portCONTEXT_SIZE
    mret

/* ----------------------------------------------------------------
 * freertos_risc_v_trap_handler  (SMP)
 *
 * Handles:
 *   Machine timer interrupt   (mcause = 0x8000…0007): tick + switch
 *   Machine software interrupt (mcause = 0x8000…0003): IPI yield
 *   M-mode ecall              (mcause = 11): voluntary yield
 *   Other:                    forwarded to application handlers
 * ---------------------------------------------------------------- */
.section .text.freertos_risc_v_trap_handler
.align 8
freertos_risc_v_trap_handler:
    portSMPsaveContextInternal

    csrr    a0, mcause
    csrr    a1, mepc

    /* mcause bit63=1 → asynchronous interrupt; bit63=0 → synchronous exception */
    bge     a0, x0, .Lsmp_sync

.Lsmp_async:
    store_x a1, 0(sp)          /* save unmodified mepc */
    csrr    t0, mhartid
    slli    t1, t0, portWORD_SIZE_LOG2
    la      t2, xISRStackTops
    add     t2, t2, t1
    load_x  sp, 0(t2)          /* switch to per-core ISR stack */
    j       .Lsmp_irq

.Lsmp_sync:
    addi    a1, a1, 4          /* advance mepc past faulting instruction */
    store_x a1, 0(sp)
    csrr    t0, mhartid
    slli    t1, t0, portWORD_SIZE_LOG2
    la      t2, xISRStackTops
    add     t2, t2, t1
    load_x  sp, 0(t2)
    j       .Lsmp_exc

/* ---- Interrupt dispatch ---- */
.Lsmp_irq:
#if ( portasmHAS_MTIME != 0 )
    /* Test for machine timer: mcause == (1<<63)|7 */
    addi    t0, x0, 1
    slli    t0, t0, __riscv_xlen - 1
    addi    t1, t0, 7
    bne     a0, t1, .Lsmp_test_msip

    portSMPupdateMtimerCompareRegister

    /* Only hart 0 drives the FreeRTOS tick counter; secondaries sync via MSIP. */
    csrr    t0, mhartid
    bnez    t0, .Lsmp_done

    call    xPortTimerTickHandler
    beqz    a0, .Lsmp_done

    csrr    a0, mhartid
    call    vTaskSwitchContext
    j       .Lsmp_done
#endif /* portasmHAS_MTIME */

.Lsmp_test_msip:
    /* Test for machine software interrupt: mcause == (1<<63)|3 */
    addi    t0, x0, 1
    slli    t0, t0, __riscv_xlen - 1
    addi    t1, t0, 3
    bne     a0, t1, .Lsmp_app_irq

    /* Clear MSIP for this hart then yield. */
    li      t0, portCLINT_MSIP_BASE
    csrr    t1, mhartid
    slli    t2, t1, 2
    add     t0, t0, t2
    sw      x0, 0(t0)

    csrr    a0, mhartid
    call    vTaskSwitchContext
    j       .Lsmp_done

.Lsmp_app_irq:
    call    freertos_risc_v_application_interrupt_handler
    j       .Lsmp_done

/* ---- Exception dispatch ---- */
.Lsmp_exc:
    li      t0, 11             /* M-mode ecall */
    bne     a0, t0, .Lsmp_app_exc
    csrr    a0, mhartid
    call    vTaskSwitchContext
    j       .Lsmp_done

.Lsmp_app_exc:
    call    freertos_risc_v_application_exception_handler

.Lsmp_done:
    portSMPrestoreContext

/* ================================================================
 * SINGLE-CORE PATH  (configNUMBER_OF_CORES == 1 or not defined)
 * ================================================================ */
#else /* single-core */

.extern vTaskSwitchContext
.extern xTaskIncrementTick
.extern pullMachineTimerCompareRegister
.extern pullNextTime
.extern uxTimerIncrementsForOneTick

/* portUPDATE_MTIMER_COMPARE_REGISTER — scalar version (upstream portASM.S). */
.macro portUPDATE_MTIMER_COMPARE_REGISTER
    load_x  a0, pullMachineTimerCompareRegister
    load_x  a1, pullNextTime
#if ( __riscv_xlen == 32 )
    li      a4, -1
    lw      a2, 0(a1)
    lw      a3, 4(a1)
    sw      a4, 0(a0)
    sw      a3, 4(a0)
    sw      a2, 0(a0)
    lw      t0, uxTimerIncrementsForOneTick
    add     a4, t0, a2
    sltu    t1, a4, a2
    add     t2, a3, t1
    sw      a4, 0(a1)
    sw      t2, 4(a1)
#endif
#if ( __riscv_xlen == 64 )
    ld      t2, 0(a1)
    sd      t2, 0(a0)
    load_x  t0, uxTimerIncrementsForOneTick
    add     t4, t0, t2
    sd      t4, 0(a1)
#endif
    .endm

/* ----------------------------------------------------------------
 * xPortStartFirstTask  (single-core)
 * Restores task context and enters the first task using ret.
 * Interrupts are enabled by writing MIE into mstatus before ret.
 * ---------------------------------------------------------------- */
.section .text.xPortStartFirstTask
xPortStartFirstTask:
    load_x  sp, pxCurrentTCB
    load_x  sp, 0(sp)

    /* Slot 0 (mepc) is used as the function return address for ret. */
    load_x  x1, 0(sp)

    portasmRESTORE_ADDITIONAL_REGISTERS

    load_x  x5, 1 * portWORD_SIZE( sp )
    addi    x5, x5, 0x08        /* set MIE bit */
    csrw    mstatus, x5         /* interrupts enabled from here */

    load_x  x7,   5 * portWORD_SIZE( sp )
    load_x  x8,   6 * portWORD_SIZE( sp )
    load_x  x9,   7 * portWORD_SIZE( sp )
    load_x  x10,  8 * portWORD_SIZE( sp )
    load_x  x11,  9 * portWORD_SIZE( sp )
    load_x  x12, 10 * portWORD_SIZE( sp )
    load_x  x13, 11 * portWORD_SIZE( sp )
    load_x  x14, 12 * portWORD_SIZE( sp )
    load_x  x15, 13 * portWORD_SIZE( sp )
#ifndef __riscv_32e
    load_x  x16, 14 * portWORD_SIZE( sp )
    load_x  x17, 15 * portWORD_SIZE( sp )
    load_x  x18, 16 * portWORD_SIZE( sp )
    load_x  x19, 17 * portWORD_SIZE( sp )
    load_x  x20, 18 * portWORD_SIZE( sp )
    load_x  x21, 19 * portWORD_SIZE( sp )
    load_x  x22, 20 * portWORD_SIZE( sp )
    load_x  x23, 21 * portWORD_SIZE( sp )
    load_x  x24, 22 * portWORD_SIZE( sp )
    load_x  x25, 23 * portWORD_SIZE( sp )
    load_x  x26, 24 * portWORD_SIZE( sp )
    load_x  x27, 25 * portWORD_SIZE( sp )
    load_x  x28, 26 * portWORD_SIZE( sp )
    load_x  x29, 27 * portWORD_SIZE( sp )
    load_x  x30, 28 * portWORD_SIZE( sp )
    load_x  x31, 29 * portWORD_SIZE( sp )
#endif
    load_x  x5, portCRITICAL_NESTING_OFFSET * portWORD_SIZE( sp )
    load_x  x6, pxCriticalNesting
    store_x x5, 0(x6)

    load_x  x5, 3 * portWORD_SIZE( sp )
    load_x  x6, 4 * portWORD_SIZE( sp )
    addi    sp, sp, portCONTEXT_SIZE
    ret

/* ----------------------------------------------------------------
 * Legacy per-vector entry points (used only if mtvec is in vectored
 * mode; not used in this project, but exported for completeness).
 * ---------------------------------------------------------------- */
.section .text.freertos_risc_v_exception_handler
.global freertos_risc_v_exception_handler
freertos_risc_v_exception_handler:
    portcontextSAVE_EXCEPTION_CONTEXT
    li      t0, 11
    bne     a0, t0, .Lsc_other_exc
    call    vTaskSwitchContext
    portcontextRESTORE_CONTEXT
.Lsc_other_exc:
    call    freertos_risc_v_application_exception_handler
    portcontextRESTORE_CONTEXT

.section .text.freertos_risc_v_interrupt_handler
.global freertos_risc_v_interrupt_handler
freertos_risc_v_interrupt_handler:
    portcontextSAVE_INTERRUPT_CONTEXT
    call    freertos_risc_v_application_interrupt_handler
    portcontextRESTORE_CONTEXT

.section .text.freertos_risc_v_mtimer_interrupt_handler
.global freertos_risc_v_mtimer_interrupt_handler
freertos_risc_v_mtimer_interrupt_handler:
    portcontextSAVE_INTERRUPT_CONTEXT
    portUPDATE_MTIMER_COMPARE_REGISTER
    call    xTaskIncrementTick
    beqz    a0, .Lsc_no_switch
    call    vTaskSwitchContext
.Lsc_no_switch:
    portcontextRESTORE_CONTEXT

/* ----------------------------------------------------------------
 * freertos_risc_v_trap_handler  (single-core)
 * Direct-mode mtvec target — handles all machine traps.
 * ---------------------------------------------------------------- */
.section .text.freertos_risc_v_trap_handler
.align 8
freertos_risc_v_trap_handler:
    portcontextSAVE_CONTEXT_INTERNAL

    csrr    a0, mcause
    csrr    a1, mepc

    bge     a0, x0, .Lsc_sync

.Lsc_async:
    store_x a1, 0(sp)
    load_x  sp, xISRStackTop
    j       .Lsc_irq

.Lsc_sync:
    addi    a1, a1, 4
    store_x a1, 0(sp)
    load_x  sp, xISRStackTop
    j       .Lsc_exc

.Lsc_irq:
#if ( portasmHAS_MTIME != 0 )
    addi    t0, x0, 1
    slli    t0, t0, __riscv_xlen - 1
    addi    t1, t0, 7
    bne     a0, t1, .Lsc_app_irq

    portUPDATE_MTIMER_COMPARE_REGISTER
    call    xTaskIncrementTick
    beqz    a0, .Lsc_done
    call    vTaskSwitchContext
    j       .Lsc_done
#endif

.Lsc_app_irq:
    call    freertos_risc_v_application_interrupt_handler
    j       .Lsc_done

.Lsc_exc:
    li      t0, 11
    bne     a0, t0, .Lsc_app_exc
    call    vTaskSwitchContext
    j       .Lsc_done

.Lsc_app_exc:
    call    freertos_risc_v_application_exception_handler

.Lsc_done:
    portcontextRESTORE_CONTEXT

#endif /* configNUMBER_OF_CORES */
