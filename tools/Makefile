BUILD_DIR ?= ../build/tools
CFLAGS    = -O3 -g -Wall -I../FreeRTOS-Trace
LDFLAGS   =

SRC     = gentrace.c
OBJECTS = $(BUILD_DIR)/gentrace.o
EXE     = $(BUILD_DIR)/gentrace

.PHONY: all clean distclean

all: $(EXE)

$(EXE): $(OBJECTS)
	mkdir -p $(BUILD_DIR)
	$(CC) $(CFLAGS) $(LDFLAGS) -o $@ $^

$(BUILD_DIR)/%.o: %.c
	mkdir -p $(BUILD_DIR)
	$(CC) -c -o $@ $< $(CFLAGS)

clean:
	-$(RM) $(OBJECTS) $(EXE)

distclean: clean

