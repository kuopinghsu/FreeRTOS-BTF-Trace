CXX ?= g++
CC ?= gcc

CXXFLAGS ?= -O3 -march=native -g -std=c++17 -Wall -Wextra -pedantic
CFLAGS ?= -O3 -march=native -g -Wall -Wextra -pedantic
CPPFLAGS ?=
LDFLAGS ?=

BUILD_DIR ?= ../build/sim
TARGET := $(BUILD_DIR)/riscv64-sim
OBJS := $(BUILD_DIR)/main.o $(BUILD_DIR)/simulator.o $(BUILD_DIR)/gdb_stub.o $(BUILD_DIR)/riscv-dis.o

.PHONY: all clean

all: $(TARGET)

$(TARGET): $(OBJS)
	mkdir -p $(dir $@)
	$(CXX) $(LDFLAGS) -o $@ $(OBJS)

$(BUILD_DIR)/main.o: main.cpp simulator.h gdb_stub.h
	mkdir -p $(dir $@)
	$(CXX) $(CPPFLAGS) $(CXXFLAGS) -c -o $@ $<

$(BUILD_DIR)/simulator.o: simulator.cpp simulator.h gdb_stub.h riscv-dis.h
	mkdir -p $(dir $@)
	$(CXX) $(CPPFLAGS) $(CXXFLAGS) -c -o $@ $<

$(BUILD_DIR)/riscv-dis.o: riscv-dis.cpp riscv-dis.h
	mkdir -p $(dir $@)
	$(CXX) $(CPPFLAGS) $(CXXFLAGS) -c -o $@ $<

$(BUILD_DIR)/gdb_stub.o: gdb_stub.c gdb_stub.h
	mkdir -p $(dir $@)
	$(CC) $(CPPFLAGS) $(CFLAGS) -c -o $@ $<

clean:
	rm -rf $(BUILD_DIR)