CORES        ?= 1
SIM          ?= ../build/sim/riscv64-sim
RISCV_PREFIX ?= /opt/xpack-riscv-none-elf-gcc-15.2.0-1/bin/riscv-none-elf-

# Max events for CORES=16 example
MAX_TRACE_EVENTS ?= 400000

.PHONY: all clean list run

all:
	$(MAKE) -C examples all CORES=$(CORES) RISCV_PREFIX=$(RISCV_PREFIX) MAX_TRACE_EVENTS=$(MAX_TRACE_EVENTS)

clean:
	$(MAKE) -C examples clean

list:
	$(MAKE) -C examples list

run:
	$(MAKE) -C ../sim
	$(MAKE) -C examples run CORES=$(CORES) SIM=$(abspath $(SIM)) RISCV_PREFIX=$(RISCV_PREFIX) MAX_TRACE_EVENTS=$(MAX_TRACE_EVENTS)

