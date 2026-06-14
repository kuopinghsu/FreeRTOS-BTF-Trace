#ifndef __SET_EXTENSIONS_H__
#define __SET_EXTENSIONS_H__

/* ------------------------------------------------------------------
 * CLINT / MTIME addresses for this chip (riscv64-sim platform).
 * Override with #ifndef guards before including port headers.
 *
 *   mtime    at 0x0200BFF8  (CLINT base 0x02000000 + 0xBFF8)
 *   mtimecmp at 0x02004000  (CLINT base + 0x4000, per-hart, 8 bytes)
 * ------------------------------------------------------------------ */
#ifndef configMTIME_BASE_ADDRESS
#define configMTIME_BASE_ADDRESS     ( 0x0200BFF8UL )
#endif

#ifndef configMTIMECMP_BASE_ADDRESS
#define configMTIMECMP_BASE_ADDRESS  ( 0x02004000UL )
#endif

#ifdef __ASSEMBLER__

#define portasmHAS_MTIME 1
#define portasmHANDLE_INTERRUPT 0
#define portasmHAS_SIFIVE_CLINT 1

#define portasmADDITIONAL_CONTEXT_SIZE 0 /* Must be even number on 32-bit cores. */

.macro portasmSAVE_ADDITIONAL_REGISTERS
    /* No additional registers to save, so this macro does nothing. */
    .endm

.macro portasmRESTORE_ADDITIONAL_REGISTERS
    /* No additional registers to restore, so this macro does nothing. */
    .endm

#else /* !__ASSEMBLER__ */

#define portasmHAS_MTIME 1
#define portasmHANDLE_INTERRUPT 0
#define portasmHAS_SIFIVE_CLINT 1

#define portasmADDITIONAL_CONTEXT_SIZE 0 /* Must be even number on 32-bit cores. */

#endif /* __ASSEMBLER__ */

#endif // __SET_EXTENSIONS_H__
