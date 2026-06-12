ENTRY(_start)

STACK_STRIDE = 16K;
MAX_HARTS = 16;
STACK_RESERVE = STACK_STRIDE * MAX_HARTS;

MEMORY
{
    RAM (rwx)  : ORIGIN = 0x80000000, LENGTH = 16M - 4K
    HTIF (rw)  : ORIGIN = 0x80000000 + 16M - 4K, LENGTH = 4K
}

PHDRS
{
    text PT_LOAD FLAGS(5); /* R-X */
    data PT_LOAD FLAGS(6); /* RW- */
}

SECTIONS
{
    .text : ALIGN(8)
    {
        KEEP(*(.init))
        KEEP(*(.init.*))
        *(.text .text.*)
        *(.rodata .rodata.*)
        KEEP(*(.fini))
        KEEP(*(.fini.*))
    } > RAM :text

    . = ALIGN(8);
    __data_load = .;

    .data : ALIGN(8)
    {
        __data_start = .;
        *(.data .data.*)
        __data_end = .;
    } > RAM :data

    . = ALIGN(8);

    .bss (NOLOAD) : ALIGN(8)
    {
        __bss_start = .;
        *(.bss .bss.*)
        *(COMMON)
        . = ALIGN(8);
        __bss_end = .;
    } > RAM :data

    . = ALIGN(16);
    __heap_start = .;

    . = ORIGIN(RAM) + LENGTH(RAM) - STACK_RESERVE;
    __heap_end = .;

    . = ORIGIN(RAM) + LENGTH(RAM);
    __stack_top = .;

    .htif (NOLOAD) : ALIGN(64)
    {
        __htif_start = .;
        KEEP(*(.htif))
        . = ALIGN(64);
        __htif_end = .;
    } > HTIF

    PROVIDE(tohost = __htif_start);
    PROVIDE(fromhost = __htif_start + 8);

    PROVIDE(end = __heap_start);
    PROVIDE(_end = __heap_start);

    /* FreeRTOS RISC-V port: ISR stack top (hart 0 uses the top of RAM) */
    PROVIDE(__freertos_irq_stack_top = __stack_top);
}
