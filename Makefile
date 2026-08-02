FREERTOS_VER ?= V11.3.0
RISCV_PREFIX ?= /opt/xpack-riscv-none-elf-gcc-15.2.0-1/bin/riscv-none-elf-

.DEFAULT_GOAL := all

.PHONY: all help run check clean distclean

help:
	@echo "FreeRTOS-BTF-Trace — make targets"
	@echo ""
	@echo "  make              Build Demo, tools, and sim (default)"
	@echo "  make run          Build all, then run the Demo in the simulator"
	@echo "  make check        Clone FreeRTOS-Kernel if missing"
	@echo "  make clean        Remove build/ and tracedata/trace.*"
	@echo "  make distclean    clean + remove FreeRTOS-Kernel/"
	@echo "  make help         Show this help"
	@echo ""
	@echo "Variables:"
	@echo "  FREERTOS_VER=$(FREERTOS_VER)"
	@echo "  RISCV_PREFIX=$(RISCV_PREFIX)"
	@echo ""
	@echo "BTF Viewer (separate tree):"
	@echo "  make -C BTFViewer help"

all: check
	$(MAKE) -C Demo RISCV_PREFIX=$(RISCV_PREFIX)
	$(MAKE) -C tools BUILD_DIR=$(abspath build/tools)
	$(MAKE) -C sim

run: all
	$(MAKE) -C Demo run RISCV_PREFIX=$(RISCV_PREFIX)

update:
	$(MAKE) -f Makefile CORES=1 clean run
	@mv tracedata/trace.btf tracedata/example.btf
	@mv tracedata/trace.vcd tracedata/example.vcd
	$(MAKE) -f Makefile CORES=4 clean run
	@mv tracedata/trace.btf tracedata/example-4cores.btf
	@mv tracedata/trace.vcd tracedata/example-4cores.vcd
	$(MAKE) -f Makefile CORES=8 clean run
	@mv tracedata/trace.btf tracedata/example-8cores.btf
	@mv tracedata/trace.vcd tracedata/example-8cores.vcd
	$(MAKE) -f Makefile CORES=16 clean run
	@mv tracedata/trace.btf tracedata/example-16cores.btf
	@mv tracedata/trace.vcd tracedata/example-16cores.vcd
	$(MAKE) -f Makefile CORES=32 clean run
	@mv tracedata/trace.btf tracedata/example-32cores.btf
	@mv tracedata/trace.vcd tracedata/example-32cores.vcd
	$(MAKE) -C BTFViewer update-images

check:
	[ -d FreeRTOS-Kernel ] || git clone -b ${FREERTOS_VER} https://github.com/FreeRTOS/FreeRTOS-Kernel.git FreeRTOS-Kernel

clean:
	-rm -rf build tracedata/trace.*

distclean:
	-rm -rf FreeRTOS-Kernel

