FREERTOS_VER ?= V10.4.5

all: check
	make -C Demo

check:
	[ -d FreeRTOS-Kernel ] || git clone -b ${FREERTOS_VER} https://github.com/FreeRTOS/FreeRTOS-Kernel.git FreeRTOS-Kernel

clean:
	make -C Demo clean

distclean:
	rm -rf FreeRTOS-Kernel

