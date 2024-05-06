FREERTOS_VER ?= V11.1.0

all: check
	make -C Demo
	make -C tools
	make -C rvsim

run: all
	make -C Demo run

check:
	[ -d FreeRTOS-Kernel ] || git clone -b ${FREERTOS_VER} https://github.com/FreeRTOS/FreeRTOS-Kernel.git FreeRTOS-Kernel

clean:
	make -C Demo clean
	make -C tools clean
	make -C rvsim clean
	-rm tracedata/trace.*

distclean:
	-rm -rf FreeRTOS-Kernel

