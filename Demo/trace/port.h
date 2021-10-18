// Copyright (c) 2021 Kuoping Hsu
//
// Permission is hereby granted, free of charge, to any person obtaining a copy
// of this software and associated documentation files (the "Software"), to deal
// in the Software without restriction, including without limitation the rights
// to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
// copies of the Software, and to permit persons to whom the Software is
// furnished to do so, subject to the following conditions:
//
// The above copyright notice and this permission notice shall be included in all
// copies or substantial portions of the Software.
//
// THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
// IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
// FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
// AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
// LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
// OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
// SOFTWARE.

#ifndef __PORT_H__
#define __PORT_H__

// This is only for srv32 simulator
#ifdef __riscv
#ifndef portGET_RUN_TIME_COUNTER_VALUE
#define portGET_RUN_TIME_COUNTER_VALUE() ({int cycles; asm volatile ("rdcycle %0" : "=r"(cycles)); cycles; })
#endif

// get time in nano seconds
#define xGetTime() (uint32_t)((uint64_t)portGET_RUN_TIME_COUNTER_VALUE()*1000000/configCPU_CLOCK_HZ)

#define HAVE_SYS_DUMP

// syscall for memory dumping
static void sys_dump(int start_addr, int size) {
    int end_addr = start_addr + size;
    asm volatile("addi a0, %[start], 0\n"
                 "addi a1, %[end], 0\n"
                 "li a7, 0x99\n"
                 "ecall\n"
                 : : [start] "r"(start_addr), [end] "r"(end_addr));
}

#else

#error "needs to implement the xGetTime() API"

#define xGetTime() 0
#undef HAVE_SYS_DUMP

#endif

#endif // __PORT_H__
