CORES        ?= 1
TICKLESS     ?= 0
SIM          ?= ../build/sim/riscv64-sim
RISCV_PREFIX ?= /opt/xpack-riscv-none-elf-gcc-15.2.0-1/bin/riscv-none-elf-

# Max events for large SMP examples (raise for CORES=16 long runs)
MAX_TRACE_EVENTS ?= 2400000

.PHONY: all clean list run

all:
	$(MAKE) -C examples all CORES=$(CORES) TICKLESS=$(TICKLESS) RISCV_PREFIX=$(RISCV_PREFIX) MAX_TRACE_EVENTS=$(MAX_TRACE_EVENTS)

clean:
	$(MAKE) -C examples clean CORES=$(CORES) TICKLESS=$(TICKLESS)

list:
	$(MAKE) -C examples list

run:
	$(MAKE) -C ../sim
	$(MAKE) -C examples run CORES=$(CORES) TICKLESS=$(TICKLESS) SIM=$(abspath $(SIM)) RISCV_PREFIX=$(RISCV_PREFIX) MAX_TRACE_EVENTS=$(MAX_TRACE_EVENTS)

