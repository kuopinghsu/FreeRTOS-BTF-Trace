// Copyright © 2020 Kuoping Hsu
// ELF reader
//
// Permission is hereby granted, free of charge, to any person obtaining a copy
// of this software and associated documentation files (the “Software”), to deal
// in the Software without restriction, including without limitation the rights
// to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
// copies of the Software, and to permit persons to whom the Software is
// furnished to do so, subject to the following conditions:
//
// The above copyright notice and this permission notice shall be included in
// all copies or substantial portions of the Software.
//
// THE SOFTWARE IS PROVIDED “AS IS”, WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
// IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
// FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
// AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
// LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
// OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
// SOFTWARE.

#include <stdlib.h>
#include <stdio.h>
#include <string.h>
#include "elf.h"
#include "opcode.h"
#include "rvsim.h"

#ifndef VERBOSE
#define VERBOSE 0
#endif

#ifndef LIBRARY
#define LIBRARY 1
#endif

static int elf32_read(FILE *fp, struct rv *rv)
{
    int i;
    Elf32_Ehdr elf32_header;
    Elf32_Phdr *elf32_phdr = NULL;
    Elf32_Phdr *ph;

    fseek(fp, 0, SEEK_SET);
    if (!fread(&elf32_header, sizeof(Elf32_Ehdr), 1, fp)) {
        // LCOV_EXCL_START
        printf("File read fail\n");
        goto fail;
        // LCOV_EXCL_STOP
    }

    if (!(elf32_phdr =
           (Elf32_Phdr*)malloc(sizeof(Elf32_Phdr) * elf32_header.e_phnum))) {
        // LCOV_EXCL_START
        goto fail;
        // LCOV_EXCL_STOP
    }

    fseek(fp, elf32_header.e_phoff, SEEK_SET);
    if (!fread(elf32_phdr,
               sizeof(Elf32_Phdr) * elf32_header.e_phnum, 1, fp)) {
        // LCOV_EXCL_START
        printf("File read fail\n");
        goto fail;
        // LCOV_EXCL_STOP
    }

    for(i = 0, ph = elf32_phdr; i < elf32_header.e_phnum; i++, ph++) {
        void *ptr;
        if (VERBOSE) printf("[%d] 0x%08x 0x%08x 0x%08x 0x%08x\n", i,
                            (int)ph->p_type,
                            (int)ph->p_offset,
                            (int)ph->p_vaddr,
                            (int)ph->p_memsz);

        if (ph->p_type != PT_LOAD)
            continue;

        fseek(fp, ph->p_offset, SEEK_SET);

        if ((ptr = malloc(ph->p_memsz)) == NULL) {
            // LCOV_EXCL_START
            printf("malloc fail!\n");
            goto fail;
            // LCOV_EXCL_STOP
        }
        if(!fread((void*)ptr, (int)ph->p_memsz, 1, fp)) {
            // LCOV_EXCL_START
            printf("File read fail\n");
            goto fail;
            // LCOV_EXCL_STOP
        }

        if (srv32_write_mem(rv, ph->p_vaddr, ph->p_memsz, (void*)ptr)) {
            if (VERBOSE) printf("load memory, address 0x%08x, size %d\n",
                                (int)ph->p_vaddr, (int)ph->p_memsz);
        } else {
            // LCOV_EXCL_START
            printf("Error: memory %08x with size %d out of range\n",
                    (int)ph->p_vaddr, (int)ph->p_memsz);
            exit(-1);
            // LCOV_EXCL_STOP
        }
        free(ptr);
    }

    if (elf32_phdr) free(elf32_phdr);
    return 1;

// LCOV_EXCL_START
fail:
    if (elf32_phdr) free(elf32_phdr);
    return 0;
// LCOV_EXCL_STOP
}

int elfloader(char *file, struct rv *rv)
{
    FILE *fp;
    char elf_header[EI_NIDENT];

    if ((fp = fopen(file, "rb")) == NULL) {
        // LCOV_EXCL_START
        printf("Can not open file %s\n", file);
        return 0;
        // LCOV_EXCL_STOP
    }

    if (!fread(&elf_header, sizeof(elf_header), 1, fp)) {
        // LCOV_EXCL_START
        printf("Can not read file %s\n", file);
        fclose(fp);
        return 0;
        // LCOV_EXCL_STOP
    }

    if (elf_header[0] == 0x7F || elf_header[1] == 'E') {
        if (elf_header[EI_CLASS] == 1) { // ELF32
            int result = elf32_read(fp, rv);
            fclose(fp);
            return result;
        } else { // ELF64
            // LCOV_EXCL_START
            return 0;
            // LCOV_EXCL_STOP
        }
    } else {
        // LCOV_EXCL_START
        printf("The file %s is not an ELF format\n", file);
        fclose(fp);
        return 0;
        // LCOV_EXCL_STOP
    }

    fclose(fp);
    return 1;
}

