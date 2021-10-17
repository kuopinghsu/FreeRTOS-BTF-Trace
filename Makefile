FREERTOS_VER ?= V10.4.5

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

distclean:
	rm -rf FreeRTOS-Kernel

