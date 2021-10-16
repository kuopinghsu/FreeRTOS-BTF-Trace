include ./Makefile.common

FREERTOS_SRC = \
    $(FREERTOS_SOURCE_DIR)/croutine.c \
    $(FREERTOS_SOURCE_DIR)/list.c \
    $(FREERTOS_SOURCE_DIR)/queue.c \
    $(FREERTOS_SOURCE_DIR)/tasks.c \
    $(FREERTOS_SOURCE_DIR)/timers.c \
    $(FREERTOS_SOURCE_DIR)/stream_buffer.c \
    $(FREERTOS_SOURCE_DIR)/event_groups.c \
    $(FREERTOS_SOURCE_DIR)/portable/MemMang/heap_3.c

PORT_SRC = $(FREERTOS_SOURCE_DIR)/portable/GCC/RISC-V/port.c \
	   trace/btf_trace.c \
           Common/port.c \
           Common/syscall.c \
           Common/printf.c \

PORT_ASM = $(FREERTOS_SOURCE_DIR)/portable/GCC/RISC-V/portASM.S \
           Common/crt0.S

DEMO_SRC = $(wildcard examples/*.c)

RTOS_OBJ = $(FREERTOS_SRC:.c=.o)
PORT_OBJ = $(PORT_SRC:.c=.o)
PORT_ASM_OBJ = $(PORT_ASM:.S=.o)
DEMO_OBJ = $(DEMO_SRC:.c=.o)
OBJS = $(PORT_ASM_OBJ) $(PORT_OBJ) $(RTOS_OBJ)
FREERTOS_LIBRARY = libfreertos.a

INCLUDES = \
    -I$(FREERTOS_SOURCE_DIR)/include \
    -I$(FREERTOS_SOURCE_DIR)/portable/GCC/RISC-V \
    -I./Common \
    -I./trace \
    -I./conf \
    -I./examples

CFLAGS   = -O2 -g -Wall $(INCLUDES) $(RISCV_GCC_OPTS)
LDFLAGS  = -L. -T Common/link.ld $(RISCV_GCC_OPTS)
LIBS     = -lfreertos -lm -lc -lgcc
PROG	 = $(DEMO_SRC:.c=.elf)

.PHONY: 

all: $(FREERTOS_LIBRARY) $(PROG) 

%.o: %.c
	$(CC) -c $(CFLAGS) -o $@ $<

%.o: %.S
	$(CC) -c $(CFLAGS) -o $@ $<

$(FREERTOS_LIBRARY): $(PORT_ASM_OBJ) $(PORT_OBJ) $(RTOS_OBJ)
	$(AR) rcs $@ $(PORT_ASM_OBJ) $(PORT_OBJ) $(RTOS_OBJ)

%.elf: Makefile
	$(CC) -o $@ $(@:.elf=.c) $(CFLAGS) $(LDFLAGS) $(LIBS)
	$(OBJDUMP) -d $@ > $@.dis

clean:
	$(RM) -f $(OBJS) $(FREERTOS_LIBRARY) examples/*.elf examples/*.elf.dis

