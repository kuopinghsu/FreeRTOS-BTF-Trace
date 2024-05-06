OUTPUT_ARCH( "riscv" )
ENTRY(_start)
_start = 0;
_MEMSIZE = 256K;
_START_ADDR = 0x00000000;

MEMORY
{
  imem : ORIGIN = _START_ADDR, LENGTH = _MEMSIZE
  dmem : ORIGIN = _START_ADDR + _MEMSIZE, LENGTH = _MEMSIZE
}

SECTIONS
{
  /* text: test code section */
  .reset :
  {
    _text_start = .;
    _start = .;
    *(.reset)
  } > imem

  .text :
  {
    *(.text .stub .text.* .gnu.linkonce.t.*)
    KEEP (*(.text.*personality*))
    *(.gnu.warning)
  } > imem

  _text_end = .;

  /* data segment */
  .data :
  {
    _data_start = .;
    __CTOR_LIST__ = .;
    ___CTOR_LIST__ = .;
    /* In 3.4.4, libgcc2.c actually required -1 here, rather than the count,
       as in ld documentation
    */
    LONG(-1)
    *(.ctors)
    LONG(0)
    __CTOR_END__ = .;

    __DTOR_LIST__ = .;
    ___DTOR_LIST__ = .;
    LONG(-1)
    *(.dtors)
    LONG(0)
    __DTOR_END__ = .;

    *(.eh_frame_hdr) *(.eh_frame_entry .eh_frame_entry.*)
    KEEP (*(.eh_frame)) *(.eh_frame.*)
    KEEP (*(.gcc_except_table)) *(.gcc_except_table.*)

    *(.srodata .srodata.* .gnu.linkonce.r.*)
    *(.sdata .sdata.* .gnu.linkonce.s.*)
    *(.rodata .rodata.* .gnu.linkonce.r.*)
    *(.data .data.* .gnu.linkonce.d.*)
    KEEP (*(.gnu.linkonce.d.*personality*))
    . = ALIGN(32 / 8);
    _data_end = .;
  } > dmem

  .bss ALIGN(0x4) :
  {
    _bss_start = .;
    *(.dynbss)
    *(.sbss .sbss.* .gnu.linkonce.b.*)
    *(.bss .bss.* .gnu.linkonce.b.*)
    *(COMMON)
    /* Align here to ensure that the .bss section occupies space up to
       _end.  Align after .bss to ensure correct alignment even if the
       .bss section disappears because there are no input sections.  */
    . = ALIGN(32 / 8);
    _bss_end = .;
  } > dmem

  .stack ALIGN(4) (NOLOAD) :
  {
    _end        = .;
  } > dmem

  PROVIDE(__freertos_irq_stack_top = (_MEMSIZE * 2 - 8K));
  PROVIDE(_stack = (_MEMSIZE * 2));

  /DISCARD/ : { *(.note.GNU-stack) }

}

