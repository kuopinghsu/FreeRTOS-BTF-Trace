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
