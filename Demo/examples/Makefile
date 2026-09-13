RISCV_PREFIX ?= /opt/xpack-riscv-none-elf-gcc-15.2.0-1/bin/riscv-none-elf-
CC      := $(RISCV_PREFIX)gcc
AR      := $(RISCV_PREFIX)ar
OBJDUMP := $(RISCV_PREFIX)objdump

ARCH_FLAGS := -march=rv64imac_zicsr_zaamo_zalrsc -mabi=lp64 -mcmodel=medany
CFLAGS  ?= -O2 -g -ffreestanding -ffunction-sections -fdata-sections -Wall -Wextra
DEPFLAGS = -MMD -MP
CPPFLAGS +=
LDFLAGS += $(ARCH_FLAGS) -nostartfiles -Wl,--no-relax \
           -Wl,--defsym=MAX_HARTS=$(CORES) -Wl,-T,../Common/linker.ld \
           -Wl,--gc-sections
LDLIBS  += -lc -lgcc

CORES ?= 1
# The local V11.3.1 affinity patch provides a 128-bit task affinity mask.
ifeq ($(shell [ "$(CORES)" -ge 1 ] 2>/dev/null && [ "$(CORES)" -le 128 ] 2>/dev/null && echo ok),)
$(error CORES must be an integer in 1 .. 128 (got '$(CORES)'))
endif
SIM   ?= ../../build/sim/riscv64-sim

# Optional: `make CORES=N TICKLESS=0|1 …` overrides configUSE_TICKLESS_IDLE in
# FreeRTOSConfig.h (via -D).  Default 0.  Build output is keyed on TICKLESS so
# toggling 0↔1 does not require a manual clean.
TICKLESS ?= 0
ifeq ($(filter $(TICKLESS),0 1),)
$(error TICKLESS must be 0 or 1 (got '$(TICKLESS)'))
endif
FREERTOS_CPPFLAGS_TICKLESS := -DconfigUSE_TICKLESS_IDLE=$(TICKLESS)

# Use a per-CORES / per-TICKLESS output directory so switching either flag
# always triggers a full rebuild: both object files and the linked ELF are
# keyed on $(CORES) and $(TICKLESS).
OUTDIR := ../../build/demo/examples/cores$(CORES)-tickless$(TICKLESS)
OBJDIR := ../../build/demo/obj/cores$(CORES)-tickless$(TICKLESS)

# ── Common sources ─────────────────────────────────────────────────────────────
# Common/port.c only holds vApplicationGet*TaskMemory(); with
# configKERNEL_PROVIDED_STATIC_MEMORY=1 tasks.c already supplies them.
COMMON_OBJS := \
    $(OBJDIR)/common/crt0.o \
    $(OBJDIR)/common/syscall.o

EXAMPLES := freertos_test
TARGETS  := $(addprefix $(OUTDIR)/,$(addsuffix .elf,$(EXAMPLES)))

# ── FreeRTOS kernel paths ──────────────────────────────────────────────────────
FREERTOS_KERNEL  := ../../FreeRTOS-Kernel
FREERTOS_MEMMANG := $(FREERTOS_KERNEL)/portable/MemMang
FREERTOS_CONF    := ../conf
FREERTOS_CHIPS   := ../port/RISC-V
FREERTOS_TRACE   := ../../FreeRTOS-Trace
GENTRACE         ?= ../../build/tools/gentrace
TRACEDATA        := ../../tracedata
TRACE_BIN        := trace.bin
STRESS_TRACE_BIN := $(TRACEDATA)/stress-128-trace.bin
STRESS_TRACE_BTF := $(TRACEDATA)/stress-128.btf
STRESS_TRACE_VCD := $(TRACEDATA)/stress-128.vcd

# Override btf_trace.h default (4096). Passed on the compile line so the trace
# library and firmware agree on TRACE_DATA layout without editing FreeRTOSConfig.h.
MAX_TRACE_EVENTS ?= 80000

# Demo/port/RISC-V/ is self-contained (portmacro.h, portContext.h,
# freertos_risc_v_chip_specific_extensions.h all live there).
# FreeRTOS-Kernel/portable/GCC/RISC-V/ is NOT on the include path.
FREERTOS_CPPFLAGS := \
    -I$(FREERTOS_KERNEL)/include \
    -I$(FREERTOS_CHIPS) \
    -I$(FREERTOS_CONF) \
    -I$(FREERTOS_TRACE) \
    -DconfigNUMBER_OF_CORES=$(CORES) \
    -DconfigMAX_TRACE_EVENTS=$(MAX_TRACE_EVENTS) \
    $(FREERTOS_CPPFLAGS_TICKLESS)

# ── Port source selection ──────────────────────────────────────────────────────
FREERTOS_PORT_C    := $(FREERTOS_CHIPS)/port.c
FREERTOS_PORT_ASM  := $(FREERTOS_CHIPS)/portASM.S
FREERTOS_PORT_COBJ := $(OBJDIR)/freertos/port.o
FREERTOS_PORT_OBJ  := $(OBJDIR)/freertos/portASM.o

FREERTOS_C_SRCS := \
    $(FREERTOS_KERNEL)/tasks.c \
    $(FREERTOS_KERNEL)/queue.c \
    $(FREERTOS_KERNEL)/list.c \
    $(FREERTOS_KERNEL)/event_groups.c \
    $(FREERTOS_KERNEL)/timers.c \
    $(FREERTOS_PORT_C) \
    $(FREERTOS_MEMMANG)/heap_4.c \
    $(FREERTOS_TRACE)/btf_trace.c

FREERTOS_OBJS := $(patsubst %.c,$(OBJDIR)/freertos/%.o,$(notdir $(FREERTOS_C_SRCS)))

# Tell make where to find FreeRTOS C sources for pattern rules.
vpath %.c $(FREERTOS_KERNEL) $(FREERTOS_MEMMANG) $(FREERTOS_CHIPS) $(FREERTOS_TRACE)

.PHONY: all clean list run stress_128 $(EXAMPLES)

all: $(TARGETS)

clean:
	rm -rf $(OUTDIR) $(OBJDIR)
	rm -f $(TRACE_BIN)

list:
	@printf '%s\n' $(EXAMPLES)

run: $(OUTDIR)/freertos_test.elf
	$(SIM) --cores $(CORES) $<
	@if [ -f $(TRACE_BIN) ]; then \
		mkdir -p $(TRACEDATA); \
		$(GENTRACE) $(TRACE_BIN) $(TRACEDATA)/trace.btf; \
		$(GENTRACE) -v $(TRACE_BIN) $(TRACEDATA)/trace.vcd; \
		rm -f $(TRACE_BIN); \
	fi

# Always rebuild and run this dedicated target with the required topology.
stress_128:
	$(MAKE) -C ../../sim
	$(MAKE) -C ../../tools BUILD_DIR=$(abspath ../../build/tools)
	$(MAKE) CORES=128 TICKLESS=$(TICKLESS) \
		../../build/demo/examples/cores128-tickless$(TICKLESS)/stress_128.elf
	@echo "[stress128] launching 128-hart simulator (startup may take several minutes)"
	@rm -f $(TRACE_BIN)
	$(SIM) --cores 128 \
		../../build/demo/examples/cores128-tickless$(TICKLESS)/stress_128.elf
	@test -f $(TRACE_BIN) || { echo "[stress128] error: $(TRACE_BIN) was not dumped" >&2; exit 1; }
	@mkdir -p $(TRACEDATA)
	$(GENTRACE) $(TRACE_BIN) $(STRESS_TRACE_BTF)
	$(GENTRACE) -v $(TRACE_BIN) $(STRESS_TRACE_VCD)
	@mv $(TRACE_BIN) $(STRESS_TRACE_BIN)
	@echo "[stress128] raw trace: $(STRESS_TRACE_BIN)"
	@echo "[stress128] BTF trace: $(STRESS_TRACE_BTF)"
	@echo "[stress128] VCD trace: $(STRESS_TRACE_VCD)"

# Shortcut: `make [CORES=N] freertos_test` builds the ELF then runs.
$(EXAMPLES): %: $(OUTDIR)/%.elf
	$(SIM) --cores $(CORES) $<

# ── freertos_test: link with FreeRTOS kernel + BTF trace objects ───────────────
$(OUTDIR)/freertos_test.elf: \
    $(OBJDIR)/freertos_test/main.o \
    $(COMMON_OBJS) \
    $(FREERTOS_OBJS) \
    $(FREERTOS_PORT_OBJ)
	@mkdir -p $(dir $@)
	$(CC) $(LDFLAGS) -o $@ $^ $(LDLIBS)

$(OUTDIR)/stress_128.elf: \
    $(OBJDIR)/stress_128/main.o \
    $(COMMON_OBJS) \
    $(FREERTOS_OBJS) \
    $(FREERTOS_PORT_OBJ)
	@mkdir -p $(dir $@)
	$(CC) $(LDFLAGS) -o $@ $^ $(LDLIBS)

# freertos_test/main.c needs FreeRTOS and trace headers.
$(OBJDIR)/freertos_test/main.o: CPPFLAGS += $(FREERTOS_CPPFLAGS)
$(OBJDIR)/stress_128/main.o: CPPFLAGS += $(FREERTOS_CPPFLAGS)

# ── Common object rules ────────────────────────────────────────────────────────
$(OBJDIR)/common/crt0.o: ../Common/crt0.S
	@mkdir -p $(dir $@)
	$(CC) $(ARCH_FLAGS) $(CPPFLAGS) -DconfigNUMBER_OF_CORES=$(CORES) $(CFLAGS) $(DEPFLAGS) -c -o $@ $<

$(OBJDIR)/common/syscall.o: ../Common/syscall.c
	@mkdir -p $(dir $@)
	$(CC) $(ARCH_FLAGS) $(CPPFLAGS) $(CFLAGS) $(DEPFLAGS) -c -o $@ $<

# ── Example main.c objects ─────────────────────────────────────────────────────
$(OBJDIR)/%/main.o: %/main.c
	@mkdir -p $(dir $@)
	$(CC) $(ARCH_FLAGS) $(CPPFLAGS) $(CFLAGS) $(DEPFLAGS) -c -o $@ $<

# ── FreeRTOS C kernel objects (vpath locates sources) ─────────────────────────
$(OBJDIR)/freertos/%.o: %.c
	@mkdir -p $(dir $@)
	$(CC) $(ARCH_FLAGS) $(CPPFLAGS) $(FREERTOS_CPPFLAGS) $(CFLAGS) $(DEPFLAGS) -c -o $@ $<

# ── FreeRTOS port C object (explicit rule avoids vpath ambiguity) ──────────────
$(FREERTOS_PORT_COBJ): $(FREERTOS_PORT_C)
	@mkdir -p $(dir $@)
	$(CC) $(ARCH_FLAGS) $(CPPFLAGS) $(FREERTOS_CPPFLAGS) $(CFLAGS) $(DEPFLAGS) -c -o $@ $<

# ── FreeRTOS assembly port object ─────────────────────────────────────────────
$(FREERTOS_PORT_OBJ): $(FREERTOS_PORT_ASM)
	@mkdir -p $(dir $@)
	$(CC) $(ARCH_FLAGS) $(CPPFLAGS) $(FREERTOS_CPPFLAGS) $(CFLAGS) $(DEPFLAGS) -c -o $@ $<

# ── Auto-generated header dependencies ────────────────────────────────────────
-include $(shell find $(OBJDIR) -name '*.d' 2>/dev/null)
