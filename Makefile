FREERTOS_VER ?= V11.3.1
RISCV_PREFIX ?= /opt/xpack-riscv-none-elf-gcc-15.2.0-1/bin/riscv-none-elf-

# The root build and its sub-makes use POSIX shell syntax and utilities.
ifeq ($(OS),Windows_NT)
GIT_SH ?= C:/Program Files/Git/bin/sh.exe
GIT_USR_BIN ?= $(subst /bin/sh.exe,/usr/bin,$(GIT_SH))
SHELL := $(GIT_SH)
.SHELLFLAGS := -e -c
export PATH := $(GIT_USR_BIN);$(PATH)
# Preserve the configured compiler prefix when sh invokes native make.
export MSYS2_ARG_CONV_EXCL := RISCV_PREFIX=;$(MSYS2_ARG_CONV_EXCL)
NATIVE_BUILD_SHELL := "SHELL=$(SHELL)" ".SHELLFLAGS=$(.SHELLFLAGS)"
endif

.DEFAULT_GOAL := all

.PHONY: all help run check clean distclean update ci-gate docs-html

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
	@echo "  make ci-gate      Run the BTFViewer CI gate"
	@echo "  make docs-html    Rebuild BTFViewer Statistics Reference HTML"

ci-gate:
	$(MAKE) -C BTFViewer ci-gate

docs-html:
	$(MAKE) -C BTFViewer docs-html

all: check
	$(MAKE) -C Demo $(NATIVE_BUILD_SHELL) RISCV_PREFIX=$(RISCV_PREFIX)
	$(MAKE) -C tools $(NATIVE_BUILD_SHELL) BUILD_DIR=$(abspath build/tools)
	$(MAKE) -C sim $(NATIVE_BUILD_SHELL)

run: all
	$(MAKE) -C Demo $(NATIVE_BUILD_SHELL) run RISCV_PREFIX=$(RISCV_PREFIX)

update:
	$(MAKE) -f Makefile CORES=1 clean run
	@mv tracedata/trace.btf tracedata/example.btf
	@mv tracedata/trace.vcd tracedata/example.vcd
	@gzip -f tracedata/example.btf
	$(MAKE) -f Makefile CORES=2 clean run
	@mv tracedata/trace.btf tracedata/example-2cores.btf
	@gzip -f tracedata/example-2cores.btf
	$(MAKE) -f Makefile CORES=4 clean run
	@mv tracedata/trace.btf tracedata/example-4cores.btf
	@gzip -f tracedata/example-4cores.btf
	$(MAKE) -f Makefile CORES=8 clean run
	@mv tracedata/trace.btf tracedata/example-8cores.btf
	@gzip -f tracedata/example-8cores.btf
	$(MAKE) -f Makefile CORES=16 clean run
	@mv tracedata/trace.btf tracedata/example-16cores.btf
	@gzip -f tracedata/example-16cores.btf
	$(MAKE) -f Makefile CORES=8 TICKLESS=0 clean run
	@mv tracedata/trace.btf tracedata/tickful-8cores.btf
	$(MAKE) -f Makefile CORES=8 TICKLESS=1 clean run
	@mv tracedata/trace.btf tracedata/tickless-8cores.btf
	@zip tracedata/tickless-8cores.zip tracedata/tickful-8cores.btf tracedata/tickless-8cores.btf
	@$(RM) tracedata/tickful-8cores.btf tracedata/tickless-8cores.btf
	@$(RM) tracedata/trace.vcd
	$(MAKE) -C BTFViewer update-images
	$(MAKE) -C BTFViewer test

check:
	[ -d FreeRTOS-Kernel ] || git clone -b ${FREERTOS_VER} https://github.com/FreeRTOS/FreeRTOS-Kernel.git FreeRTOS-Kernel

clean:
	-rm -rf build tracedata/trace.*

distclean:
	-rm -rf FreeRTOS-Kernel
