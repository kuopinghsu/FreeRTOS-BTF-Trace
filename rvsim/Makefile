DEBUG    ?= 0
top      ?= 0
memsize  ?= 128
rv32c    ?= 0
CC        = gcc
SYS      := $(shell gcc -dumpmachine)

ifneq (, $(findstring darwin, $(SYS)))
CFLAGS  += -DMACOX
endif

ifeq ($(DEBUG), 1)
CFLAGS  += -O0 -g -Wall
else
CFLAGS  += -O3 -g -Wall
endif

ifeq ($(top), 1)
CFLAGS  += -DSINGLE_RAM
endif

ifeq ($(rv32c), 1)
CFLAGS  += -DRV32C_ENABLED
endif

SRC      = rvsim.c decompress.c elfread.c getch.c
OBJECTS  = $(SRC:.c=.o)
RVSIM   = rvsim

.SUFFIXS: .c .o

.PHONY: clean

%.o: %.c opcode.h
	$(CC) -c -o $@ $< $(CFLAGS)

$(RVSIM): $(OBJECTS)
	$(CC) $(CFLAGS) $(LDFLAGS) -o $(RVSIM) $(OBJECTS)

clean:
	-$(RM) $(OBJECTS) dump.txt trace.log $(RVSIM)

distclean: clean

