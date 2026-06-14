.equ MAX_HARTS, 16         /* must match MAX_HARTS in linker.ld */
.equ STACK_STRIDE_LOG2, 14 /* 16K per hart = 2^14; must match STACK_STRIDE in linker.ld */
.equ CLINT_MSIP_BASE, 0x02000000

.section .init
.global _start
.type _start, @function

_start:
    csrr t1, mhartid
    la sp, __stack_top
    slli t0, t1, STACK_STRIDE_LOG2  /* offset = hartid * STACK_STRIDE */
    sub sp, sp, t0

    beqz t1, .Linit_primary

    /* Non-zero harts wait until hart0 releases them via CLINT MSIP. */
    li t2, CLINT_MSIP_BASE
    slli t3, t1, 2
    add t2, t2, t3
.Lwait_release:
    lw t0, 0(t2)
    beqz t0, .Lwait_release
    sw zero, 0(t2)              /* clear MSIP, then enter the SMP secondary-hart path */
    call vPortSecondaryHartEntry
1:  wfi
    j 1b

.Linit_primary:
    /* In this simulator flow, ELF PT_LOAD is already materialized in RAM. */
    /* Skip .data copy to avoid redundant RAM-to-RAM self-copy at boot. */

    /* Zero .bss; __bss_start and __bss_end are both 8-byte aligned (linker.ld). */
    la a0, __bss_start
    la a1, __bss_end
.Lzero_bss_loop:
    bgeu a0, a1, .Lrelease_secondaries
    sd zero, 0(a0)
    addi a0, a0, 8
    j .Lzero_bss_loop

    /* Ensure all .bss stores are globally visible before waking secondary harts. */
.Lrelease_secondaries:
    fence rw, rw
    li t0, CLINT_MSIP_BASE + 4  /* start at hart 1 MSIP (hart n at base + n*4) */
    li t1, 1
    li t2, MAX_HARTS - 1        /* release harts 1 .. MAX_HARTS-1 */
.Lrelease_loop:
    sw t1, 0(t0)
    addi t0, t0, 4
    addi t2, t2, -1
    bnez t2, .Lrelease_loop

.Lenter_main:
    call main
    call _exit                  /* a0 = main() return value */

5:
    wfi
    j 5b

.size _start, . - _start

/* Weak stub for bare-metal SMP examples: secondary harts enter main().
 * FreeRTOS builds link port.c which provides the strong override. */
.section .text
.weak vPortSecondaryHartEntry
.type vPortSecondaryHartEntry, @function
vPortSecondaryHartEntry:
    call main
    call _exit                  /* a0 = main() return value */
2:  wfi
    j 2b
.size vPortSecondaryHartEntry, . - vPortSecondaryHartEntry
