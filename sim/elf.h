/* Portable ELF64 definitions for macOS (which lacks <elf.h>).
 *
 * Provides only the types and constants needed by the RISC-V simulator:
 *   Elf64_Ehdr, Elf64_Phdr, Elf64_Shdr, Elf64_Sym,
 *   ELFMAG, SELFMAG, EI_CLASS, ELFCLASS64, EM_RISCV,
 *   PT_LOAD, SHT_SYMTAB.
 */

#ifndef SIM_ELF_H
#define SIM_ELF_H

#include <cstdint>

/* EI_CLASS values */
#define EI_CLASS   4
#define ELFCLASS64 2

/* e_machine */
#define EM_RISCV 243

/* p_type / sh_type */
#define PT_LOAD    1
#define SHT_SYMTAB 2

/* ELF magic */
#define ELFMAG   "\177ELF"
#define SELFMAG  4

typedef uint16_t Elf64_Half;
typedef uint32_t Elf64_Word;
typedef uint64_t Elf64_Addr;
typedef uint64_t Elf64_Off;

typedef struct {
    unsigned char e_ident[16];
    Elf64_Half    e_type;
    Elf64_Half    e_machine;
    Elf64_Word    e_version;
    Elf64_Addr    e_entry;
    Elf64_Off     e_phoff;
    Elf64_Off     e_shoff;
    Elf64_Word    e_flags;
    Elf64_Half    e_ehsize;
    Elf64_Half    e_phentsize;
    Elf64_Half    e_phnum;
    Elf64_Half    e_shentsize;
    Elf64_Half    e_shnum;
    Elf64_Half    e_shstrndx;
} Elf64_Ehdr;

typedef struct {
    Elf64_Word  p_type;
    Elf64_Word  p_flags;
    Elf64_Off   p_offset;
    Elf64_Addr  p_vaddr;
    Elf64_Addr  p_paddr;
    Elf64_Addr  p_filesz;
    Elf64_Addr  p_memsz;
    Elf64_Addr  p_align;
} Elf64_Phdr;

typedef struct {
    Elf64_Word  sh_name;
    Elf64_Word  sh_type;
    Elf64_Addr  sh_flags;
    Elf64_Addr  sh_addr;
    Elf64_Off   sh_offset;
    Elf64_Addr  sh_size;
    Elf64_Word  sh_link;
    Elf64_Word  sh_info;
    Elf64_Addr  sh_addralign;
    Elf64_Addr  sh_entsize;
} Elf64_Shdr;

typedef struct {
    Elf64_Word  st_name;
    unsigned char st_info;
    unsigned char st_other;
    Elf64_Half  st_shndx;
    Elf64_Addr  st_value;
    Elf64_Addr  st_size;
} Elf64_Sym;

#endif /* SIM_ELF_H */
