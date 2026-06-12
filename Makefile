FREERTOS_VER ?= V11.3.0
RISCV_PREFIX ?= /opt/xpack-riscv-none-elf-gcc-15.2.0-1/bin/riscv-none-elf-

all: check
	$(MAKE) -C Demo RISCV_PREFIX=$(RISCV_PREFIX)
	$(MAKE) -C tools BUILD_DIR=$(abspath build/tools)
	$(MAKE) -C sim

run: all
	$(MAKE) -C Demo run RISCV_PREFIX=$(RISCV_PREFIX)

check:
	[ -d FreeRTOS-Kernel ] || git clone -b ${FREERTOS_VER} https://github.com/FreeRTOS/FreeRTOS-Kernel.git FreeRTOS-Kernel

clean:
	-rm -rf build tracedata/trace.*

distclean:
	-rm -rf FreeRTOS-Kernel

