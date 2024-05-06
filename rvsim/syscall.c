// Copyright © 2020 Kuoping Hsu
// rvsim.c: Instruction Set Simulator for RISC-V RV32I instruction sets
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

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <getopt.h>
#include <sys/time.h>

#include <unistd.h>
#include <sys/types.h>
#include <sys/stat.h>
#include <fcntl.h>

#include "opcode.h"
#include "rvsim.h"

void prog_exit(struct rv *rv, int exitcode);

int srv32_syscall(
    struct rv *rv,
    int func, int a0, int a1, int a2,
    int a3, int a4, int a5)
{
    int res = -1;

    (void)a3;
    (void)a4;
    (void)a5;

    void *a0_ptr = srv32_get_memptr(rv, a0);
    void *a1_ptr = srv32_get_memptr(rv, a1);

    switch(func) {
       case SYS_OPEN:
           res = (int)open((const char*)a0_ptr,
                            O_RDWR | O_CREAT /* a1 */,
                            S_IRUSR | S_IWUSR | S_IRGRP | S_IROTH /* a2 */ );
           break;
       case SYS_CLOSE:
           res = (int)close(a0);
           break;
       case SYS_LSEEK:
           res = (int)lseek(a0, a1, a2);
           break;
       case SYS_EXIT:
           prog_exit(rv, 0);
           break;
       case SYS_READ:
           #if 0
           if (a0 == STDIN) {
               int i = 0;
               char c = 0;
               do {
                   c = getch();
                   ((char*)a1_ptr)[i] = c;
               } while(++i<a2 && c != '\n');
           }
           #else
           res = (int)read(a0, (void *)(a1_ptr), a2);
           #endif
           break;
       case SYS_WRITE:
           #if 0
           if (a0 == STDOUT) {
               int i;
               for(i=0; i<a2; i++) {
                   char c = ((char*)(a1_ptr))[i];
                   putchar(c);
               }
               fflush(stdout);
           }
           #else
           res = (int)write(a0, (const char*)(a1_ptr), a2);
           #endif
           break;
       case SYS_DUMP: {
               FILE *fp;
               int *start = (int*)srv32_get_memptr(rv, a0);
               int *end   = (int*)srv32_get_memptr(rv, a1);
               if ((fp = fopen("dump.txt", "w")) == NULL) {
                   printf("Create dump.txt fail\n");
                   exit(1);
               }
               if ((a0 & 3) != 0 || (a1 & 3) != 0) {
                   printf("Alignment error on memory dumping.\n");
                   exit(1);
               }
               while(start != end)
                   fprintf(fp, "%08x\n", *start++);
               fclose(fp);
           }
           res = a1;
           break;
       case SYS_DUMP_BIN: {
               FILE *fp;
               char *start = (char*)srv32_get_memptr(rv, a0);
               char *end   = (char*)srv32_get_memptr(rv, a1);
               if ((fp = fopen("dump.bin", "wb")) == NULL) {
                   printf("Create dump.bin fail\n");
                   exit(1);
               }
               while(start != end)
                   fprintf(fp, "%c", *start++);
               fclose(fp);
           }
           res = a1;
           break;
       default:
           break;
    }
    return res;
}
