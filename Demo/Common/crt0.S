    .section .reset, "ax"
    .global _start
    .extern freertos_risc_v_trap_handler
_start:
    la      t0, freertos_risc_v_trap_handler
    csrw    mtvec, t0

    la      t0, _bss_start
    la      t1, _bss_end

_bss_clear:
    sw      zero,0(t0)
    addi    t0, t0, 4
    bltu    t0, t1, _bss_clear

    la      sp, _stack
    call    main
    tail    exit

