// ============================================================================
// File: sim/gdb_stub.c
// Project: FreeRTOS-RISCV-SMP
// Description: GDB Remote Serial Protocol stub implementation.
//
// Implements the GDB RSP server used by riscv64-sim to allow source-level
// debugging via GDB's remote target interface.
// ============================================================================

#include "gdb_stub.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
#include <sys/socket.h>
#include <netinet/in.h>
#include <arpa/inet.h>
#include <errno.h>
#include <ctype.h>
#include <inttypes.h>

#define GDB_STUB_PID 1

#if GDB_STUB_XLEN == 32
    #define GDB_REG_HEX_BYTES 4
    #define GDB_REG_HEX_CHARS 8
    #define GDB_ADDR_HEX_FMT "%08" PRIx32
    #define GDB_TARGET_ARCH "riscv:rv32"
#elif GDB_STUB_XLEN == 64
    #define GDB_REG_HEX_BYTES 8
    #define GDB_REG_HEX_CHARS 16
    #define GDB_ADDR_HEX_FMT "%016" PRIx64
    #define GDB_TARGET_ARCH "riscv:rv64"
#else
    #error "Unsupported GDB_STUB_XLEN"
#endif

// Forward declarations for static functions
static void handle_query(gdb_context_t *ctx, void *simulator, const gdb_callbacks_t *callbacks);
static void handle_general_set(gdb_context_t *ctx, void *simulator, const gdb_callbacks_t *callbacks);
static void handle_read_registers(gdb_context_t *ctx, void *simulator, const gdb_callbacks_t *callbacks);
static void handle_write_registers(gdb_context_t *ctx, void *simulator, const gdb_callbacks_t *callbacks);
static void handle_read_memory(gdb_context_t *ctx, void *simulator, const gdb_callbacks_t *callbacks);
static void handle_write_memory(gdb_context_t *ctx, void *simulator, const gdb_callbacks_t *callbacks);
static void handle_breakpoint(gdb_context_t *ctx, bool insert);
static void handle_read_single_register(gdb_context_t *ctx, void *simulator, const gdb_callbacks_t *callbacks);
static void handle_write_single_register(gdb_context_t *ctx, void *simulator, const gdb_callbacks_t *callbacks);
static void handle_write_memory_binary(gdb_context_t *ctx, void *simulator, const gdb_callbacks_t *callbacks);
static void handle_reset(gdb_context_t *ctx, void *simulator, const gdb_callbacks_t *callbacks);
static void handle_set_thread(gdb_context_t *ctx, void *simulator, const gdb_callbacks_t *callbacks);
static void handle_thread_alive(gdb_context_t *ctx, void *simulator, const gdb_callbacks_t *callbacks);
static void handle_halt_reason(gdb_context_t *ctx, void *simulator, const gdb_callbacks_t *callbacks);
static void handle_search_memory(gdb_context_t *ctx, void *simulator, const gdb_callbacks_t *callbacks);
static void handle_vcont(gdb_context_t *ctx, void *simulator,
                         const gdb_callbacks_t *callbacks, int *run_cpu);
static int send_packet(gdb_stub_t *stub, const char *data);
static int receive_packet(gdb_stub_t *stub);

// Protocol helpers
static uint8_t hex_to_int(char c) {
    if (c >= '0' && c <= '9')
        return c - '0';
    if (c >= 'a' && c <= 'f')
        return c - 'a' + 10;
    if (c >= 'A' && c <= 'F')
        return c - 'A' + 10;
    return 0;
}

static char int_to_hex(uint8_t val) {
    return val < 10 ? '0' + val : 'a' + (val - 10);
}

static gdb_addr_t parse_hex(const char *str, int len) {
    gdb_addr_t value = 0;
    for (int i = 0; i < len && str[i]; i++) {
        value = (value << 4) | hex_to_int(str[i]);
    }
    return value;
}

static gdb_reg_t parse_hex_le(const char *str, int hex_chars) {
    gdb_reg_t value = 0;
    int bytes = hex_chars / 2;
    for (int i = 0; i < bytes && str[i * 2] && str[i * 2 + 1]; i++) {
        uint8_t byte = (hex_to_int(str[i * 2]) << 4) | hex_to_int(str[i * 2 + 1]);
        value |= (gdb_reg_t)byte << (i * 8);
    }
    return value;
}

static void encode_hex(char *buf, gdb_reg_t value, int bytes) {
    // Encode in little-endian byte order (LSB first) for RISC-V
    for (int i = 0; i < bytes; i++) {
        uint8_t byte = (value >> (i * 8)) & 0xFF;
        *buf++ = int_to_hex(byte >> 4);
        *buf++ = int_to_hex(byte & 0xF);
    }
}

static uint8_t calculate_checksum(const char *data, int len) {
    uint8_t sum = 0;
    for (int i = 0; i < len; i++) {
        sum += (uint8_t)data[i];
    }
    return sum;
}

static bool ranges_overlap(gdb_addr_t addr1, gdb_addr_t len1, gdb_addr_t addr2, gdb_addr_t len2) {
    if (len1 == 0 || len2 == 0) {
        return false;
    }
    uint64_t end1 = (uint64_t)addr1 + (uint64_t)len1;
    uint64_t end2 = (uint64_t)addr2 + (uint64_t)len2;
    return addr1 < end2 && addr2 < end1;
}

static bool thread_pid_valid(int pid) {
    return pid == 0 || pid == GDB_STUB_PID;
}

static int parse_thread_spec(const char *str, int *pid, int *tid) {
    if (!str || !*str) {
        *pid = 0;
        *tid = -1;
        return 0;
    }
    if (strcmp(str, "-1") == 0) {
        *pid = 0;
        *tid = -1;
        return 0;
    }
    if (*str == 'p' || *str == 'P') {
        str++;
    }

    char *dot = (char*)strchr(str, '.');
    if (dot) {
        *pid = (int)strtol(str, NULL, 16);
        *tid = (int)strtol(dot + 1, NULL, 16);
    } else {
        *pid = 0;
        *tid = (int)strtol(str, NULL, 16);
    }
    return 0;
}

static void format_stop_reply(gdb_context_t *ctx, char *response, size_t len,
                              int signal, int tid, bool swbreak,
                              gdb_addr_t watch_addr, gdb_addr_t pc_addr) {
    if (ctx->multiprocess_active) {
        if (swbreak) {
            snprintf(response, len, "T%02xthread:p%x.%x;swbreak:;",
                     signal & 0xFF, GDB_STUB_PID, tid);
        } else if (watch_addr != 0) {
            snprintf(response, len, "T%02xthread:p%x.%x;watch:" GDB_ADDR_HEX_FMT ";",
                     signal & 0xFF, GDB_STUB_PID, tid, watch_addr);
        } else if (pc_addr != 0) {
            snprintf(response, len, "T%02xthread:p%x.%x;20:" GDB_ADDR_HEX_FMT ";",
                     signal & 0xFF, GDB_STUB_PID, tid, pc_addr);
        } else {
            snprintf(response, len, "T%02xthread:p%x.%x;",
                     signal & 0xFF, GDB_STUB_PID, tid);
        }
        return;
    }

    if (swbreak) {
        snprintf(response, len, "T%02xthread:%x;swbreak:;",
                 signal & 0xFF, tid);
    } else if (watch_addr != 0) {
        snprintf(response, len, "T%02xthread:%x;watch:" GDB_ADDR_HEX_FMT ";",
                 signal & 0xFF, tid, watch_addr);
    } else if (pc_addr != 0) {
        snprintf(response, len, "T%02xthread:%x;20:" GDB_ADDR_HEX_FMT ";",
                 signal & 0xFF, tid, pc_addr);
    } else {
        snprintf(response, len, "T%02xthread:%x;",
                 signal & 0xFF, tid);
    }
}

static int resolve_continue_thread(int pid, int tid) {
    if (!thread_pid_valid(pid)) {
        return -2;
    }
    if (tid <= 0) {
        return -1;
    }
    return tid;
}

static int resolve_step_thread(gdb_context_t *ctx, int pid, int tid) {
    int ct = resolve_continue_thread(pid, tid);
    if (ct == -2) {
        return -2;
    }
    if (ct > 0) {
        return ct;
    }
    return ctx->current_thread;
}

static int write_all(int fd, const void *buf, size_t len) {
    const uint8_t *p = (const uint8_t *)buf;
    size_t written = 0;

    while (written < len) {
        ssize_t n = write(fd, p + written, len - written);
        if (n <= 0) {
            return -1;
        }
        written += (size_t)n;
    }
    return 0;
}

// Send a packet to GDB
static int send_packet(gdb_stub_t *stub, const char *data) {
    char buffer[GDB_BUFFER_SIZE];
    int len = strlen(data);
    uint8_t checksum = calculate_checksum(data, len);

    int packet_len = snprintf(buffer, sizeof(buffer), "$%s#%02x", data, checksum);
    if (packet_len < 0 || (size_t)packet_len >= sizeof(buffer)) {
        return -1;
    }
    return write_all(stub->client_fd, buffer, (size_t)packet_len);
}

// Receive a packet from GDB
static int receive_packet(gdb_stub_t *stub) {
    char c;
    int state = 0; // 0: wait for $, 1: read data, 2: read checksum
    int index = 0;
    uint8_t checksum_expected = 0;
    uint8_t checksum_received = 0;

    while (1) {
        ssize_t nread = read(stub->client_fd, &c, 1);
        if (nread <= 0) {
            stub->consecutive_failures++;
            return -1;
        }

        switch (state) {
        case 0: // Wait for '$'
            if (c == '$') {
                state = 1;
                index = 0;
            } else if (c == 0x03) { // Ctrl-C
                stub->packet_buffer[0] = 0x03;
                stub->packet_size = 1;
                return 0;
            }
            break;

        case 1: // Read data
            if (c == '#') {
                stub->packet_buffer[index] = '\0';
                stub->packet_size = index;
                checksum_expected = calculate_checksum(stub->packet_buffer, index);
                state = 2;
                index = 0;
            } else {
                if (index < GDB_BUFFER_SIZE - 1) {
                    stub->packet_buffer[index++] = c;
                }
            }
            break;

        case 2: // Read checksum (2 hex digits)
            checksum_received = (checksum_received << 4) | hex_to_int(c);
            if (++index == 2) {
                // Verify checksum
                if (checksum_received != checksum_expected) {
                    // Send NACK if not in no-ack mode
                    if (!stub->no_ack_mode) {
                        c = '-';
                        ssize_t result = write(stub->client_fd, &c, 1);
                        if (result < 0) {
                            stub->consecutive_failures++;
                            return -1;
                        }
                    }
                    stub->consecutive_failures++;
                    return -1;
                }

                // Send ACK if not in no-ack mode
                if (!stub->no_ack_mode) {
                    c = '+';
                    ssize_t result = write(stub->client_fd, &c, 1);
                    if (result < 0) {
                        stub->consecutive_failures++;
                        return -1;
                    }
                }

                // Success - reset failure counter
                stub->consecutive_failures = 0;
                return 0;
            }
            break;
        }
    }
}

// Initialize GDB stub
int gdb_stub_init(gdb_context_t *ctx, uint16_t port) {
    memset(ctx, 0, sizeof(*ctx));
    ctx->stub.port = port;
    ctx->stub.socket_fd = -1;
    ctx->stub.client_fd = -1;
    ctx->current_thread = 1;
    ctx->continue_thread = -1;
    ctx->stop_thread = 0;

    // Create socket
    ctx->stub.socket_fd = socket(AF_INET, SOCK_STREAM, 0);
    if (ctx->stub.socket_fd < 0) {
        perror("socket");
        return -1;
    }

    // Allow reuse of address
    int opt = 1;
    setsockopt(ctx->stub.socket_fd, SOL_SOCKET, SO_REUSEADDR, &opt,
               sizeof(opt));

    // Bind to port
    struct sockaddr_in addr;
    memset(&addr, 0, sizeof(addr));
    addr.sin_family = AF_INET;
    addr.sin_addr.s_addr = INADDR_ANY;
    addr.sin_port = htons(port);

    if (bind(ctx->stub.socket_fd, (struct sockaddr *)&addr, sizeof(addr)) <
        0) {
        perror("bind");
        close(ctx->stub.socket_fd);
        return -1;
    }

    // Listen for connections
    if (listen(ctx->stub.socket_fd, 1) < 0) {
        perror("listen");
        close(ctx->stub.socket_fd);
        return -1;
    }

    ctx->stub.enabled = true;
    printf("GDB stub listening on port %d\n", port);
    return 0;
}

// Accept client connection
int gdb_stub_accept(gdb_context_t *ctx) {
    struct sockaddr_in client_addr;
    socklen_t client_len = sizeof(client_addr);

    printf("Waiting for GDB connection...\n");
    ctx->stub.client_fd =
        accept(ctx->stub.socket_fd, (struct sockaddr *)&client_addr,
               &client_len);

    if (ctx->stub.client_fd < 0) {
        perror("accept");
        return -1;
    }

    ctx->stub.connected = true;
    printf("GDB connected from %s:%d\n", inet_ntoa(client_addr.sin_addr),
           ntohs(client_addr.sin_port));

    return 0;
}

// Handle query commands
static void handle_query(gdb_context_t *ctx, void *simulator,
                         const gdb_callbacks_t *callbacks) {
    char *packet = ctx->stub.packet_buffer;

    if (strncmp(packet, "qSupported", 10) == 0) {
        const char *client_caps = packet + 10;
        if (*client_caps == ':') {
            client_caps++;
        }
        while (*client_caps == ' ') {
            client_caps++;
        }
        ctx->multiprocess_active = (strstr(client_caps, "multiprocess+") != NULL);
        send_packet(&ctx->stub,
                    "PacketSize=4096;swbreak+;multiprocess+;vContSupported+;"
                    "qXfer:features:read+;QStartNoAckMode+");
    } else if (strncmp(packet, "qAttached", 9) == 0) {
        send_packet(&ctx->stub, "1");
    } else if (strncmp(packet, "qC", 2) == 0) {
        char response[32];
        int tid = ctx->stop_thread ? ctx->stop_thread : ctx->current_thread;
        if (ctx->multiprocess_active) {
            snprintf(response, sizeof(response), "QCp%x.%x", GDB_STUB_PID, tid);
        } else {
            snprintf(response, sizeof(response), "QC%x", tid);
        }
        send_packet(&ctx->stub, response);
    } else if (strncmp(packet, "qfThreadInfo", 12) == 0) {
        char response[GDB_BUFFER_SIZE];
        int num_harts = callbacks->get_num_harts ? callbacks->get_num_harts(simulator) : 1;
        int pos;
        if (ctx->multiprocess_active) {
            pos = snprintf(response, sizeof(response), "mp%x.%x", GDB_STUB_PID, 1);
            for (int h = 2; h <= num_harts && pos > 0 && pos < (int)sizeof(response); h++) {
                pos += snprintf(response + pos, sizeof(response) - (size_t)pos,
                                ",p%x.%x", GDB_STUB_PID, h);
            }
        } else {
            pos = snprintf(response, sizeof(response), "m1");
            for (int h = 2; h <= num_harts && pos > 0 && pos < (int)sizeof(response); h++) {
                pos += snprintf(response + pos, sizeof(response) - (size_t)pos, ",%x", h);
            }
        }
        send_packet(&ctx->stub, pos > 0 ? response : "l");
    } else if (strncmp(packet, "qsThreadInfo", 12) == 0) {
        send_packet(&ctx->stub, "l");
    } else if (strncmp(packet, "qXfer:features:read:target.xml", 30) == 0) {
        const char *xml = "l<?xml version=\"1.0\"?>"
                          "<!DOCTYPE target SYSTEM \"gdb-target.dtd\">"
                          "<target version=\"1.0\">"
                          "<architecture>" GDB_TARGET_ARCH "</architecture>"
                          "</target>";
        send_packet(&ctx->stub, xml);
    } else if (strncmp(packet, "qOffsets", 8) == 0) {
        send_packet(&ctx->stub, "Text=0;Data=0;Bss=0");
    } else if (strncmp(packet, "qTStatus", 8) == 0) {
        send_packet(&ctx->stub, "T0;tnotrun:0");
    } else if (strncmp(packet, "qSearch:memory:", 15) == 0) {
        handle_search_memory(ctx, simulator, callbacks);
    } else {
        send_packet(&ctx->stub, "");
    }
}

// Handle general set commands (Q)
static void handle_general_set(gdb_context_t *ctx, void *simulator,
                               const gdb_callbacks_t *callbacks) {
    (void)simulator;
    (void)callbacks;
    char *packet = ctx->stub.packet_buffer;

    if (strncmp(packet, "QStartNoAckMode", 15) == 0) {
        ctx->stub.no_ack_mode = true;
        send_packet(&ctx->stub, "OK");
    } else {
        send_packet(&ctx->stub, ""); // Not supported
    }
}

// Read registers (g command)
static void handle_read_registers(gdb_context_t *ctx, void *simulator,
                                   const gdb_callbacks_t *callbacks) {
    char response[GDB_BUFFER_SIZE];
    char *p = response;

    // Send 33 registers (x0-x31 + pc)
    for (int i = 0; i < 32; i++) {
        gdb_reg_t value = callbacks->read_reg(simulator, i);
        encode_hex(p, value, GDB_REG_HEX_BYTES);
        p += GDB_REG_HEX_CHARS;
    }

    // Add PC
    gdb_addr_t pc = callbacks->get_pc(simulator);
    encode_hex(p, (gdb_reg_t)pc, GDB_REG_HEX_BYTES);
    p += GDB_REG_HEX_CHARS;
    *p = '\0';

    send_packet(&ctx->stub, response);
}

// Write registers (G command)
static void handle_write_registers(gdb_context_t *ctx, void *simulator,
                                    const gdb_callbacks_t *callbacks) {
    char *data = ctx->stub.packet_buffer + 1;

    for (int i = 0; i < 32; i++) {
        gdb_reg_t value = parse_hex_le(data + i * GDB_REG_HEX_CHARS, GDB_REG_HEX_CHARS);
        callbacks->write_reg(simulator, i, value);
    }

    // Write PC
    gdb_addr_t pc = (gdb_addr_t)parse_hex_le(data + 32 * GDB_REG_HEX_CHARS, GDB_REG_HEX_CHARS);
    callbacks->set_pc(simulator, pc);

    send_packet(&ctx->stub, "OK");
}

// Read memory (m command)
static void handle_read_memory(gdb_context_t *ctx, void *simulator,
                                const gdb_callbacks_t *callbacks) {
    char *packet = ctx->stub.packet_buffer + 1;
    char *comma = strchr(packet, ',');
    if (!comma) {
        send_packet(&ctx->stub, "E01");
        return;
    }

    *comma = '\0';
    gdb_addr_t addr = parse_hex(packet, comma - packet);
    gdb_addr_t len = parse_hex(comma + 1, strlen(comma + 1));

    if ((uint64_t)len > (uint64_t)(GDB_BUFFER_SIZE / 2)) {
        send_packet(&ctx->stub, "E02");
        return;
    }

    char response[GDB_BUFFER_SIZE];
    char *p = response;

    for (gdb_addr_t i = 0; i < len; i++) {
        uint8_t byte = callbacks->read_mem(simulator, addr + i, 1) & 0xFF;
        *p++ = int_to_hex(byte >> 4);
        *p++ = int_to_hex(byte & 0xF);
    }
    *p = '\0';

    send_packet(&ctx->stub, response);
}

// Write memory (M command)
static void handle_write_memory(gdb_context_t *ctx, void *simulator,
                                 const gdb_callbacks_t *callbacks) {
    char *packet = ctx->stub.packet_buffer + 1;
    char *comma = strchr(packet, ',');
    char *colon = strchr(packet, ':');

    if (!comma || !colon) {
        send_packet(&ctx->stub, "E01");
        return;
    }

    *comma = '\0';
    *colon = '\0';

    gdb_addr_t addr = parse_hex(packet, comma - packet);
    gdb_addr_t len = parse_hex(comma + 1, colon - comma - 1);
    char *data = colon + 1;

    for (gdb_addr_t i = 0; i < len; i++) {
        uint8_t byte = (hex_to_int(data[i * 2]) << 4) | hex_to_int(data[i * 2 + 1]);
        callbacks->write_mem(simulator, addr + i, byte, 1);
    }

    send_packet(&ctx->stub, "OK");
}

// Handle breakpoint commands (Z/z)
static void handle_breakpoint(gdb_context_t *ctx, bool insert) {
    char *packet = ctx->stub.packet_buffer + 1;
    char *comma1 = strchr(packet, ',');
    char *comma2 = comma1 ? strchr(comma1 + 1, ',') : NULL;

    if (!comma1 || !comma2) {
        send_packet(&ctx->stub, "E01");
        return;
    }

    *comma1 = '\0';
    *comma2 = '\0';

    int type = parse_hex(packet, comma1 - packet);
    gdb_addr_t addr = parse_hex(comma1 + 1, comma2 - comma1 - 1);
    gdb_addr_t len = parse_hex(comma2 + 1, strlen(comma2 + 1));

    if ((type >= 2 && type <= 4) && len == 0) {
        len = 4;
    }

    int result = 0;

    // Handle breakpoints (type 0, 1) and watchpoints (type 2, 3, 4)
    if (type == 0 || type == 1) {
        // Software (0) and hardware (1) breakpoints
        if (insert) {
            result = gdb_stub_add_breakpoint(ctx, addr);
        } else {
            result = gdb_stub_remove_breakpoint(ctx, addr);
        }
    } else if (type >= 2 && type <= 4) {
        // Watchpoints: 2=write, 3=read, 4=access
        if (insert) {
            result = gdb_stub_add_watchpoint(ctx, addr, len, (watchpoint_type_t)type);
        } else {
            result = gdb_stub_remove_watchpoint(ctx, addr, len, (watchpoint_type_t)type);
        }
    } else {
        // Unsupported type
        send_packet(&ctx->stub, "");
        return;
    }

    send_packet(&ctx->stub, result == 0 ? "OK" : "E01");
}

// Read single register (p command)
static void handle_read_single_register(gdb_context_t *ctx, void *simulator,
                                       const gdb_callbacks_t *callbacks) {
    char *packet = ctx->stub.packet_buffer + 1;
    int reg_num = (int)parse_hex(packet, strlen(packet));

    if (reg_num < 0 || reg_num > 32) {
        send_packet(&ctx->stub, "E01");
        return;
    }

    char response[32];
    gdb_reg_t value;

    if (reg_num < 32) {
        value = callbacks->read_reg(simulator, reg_num);
    } else if (reg_num == 32) {
        value = callbacks->get_pc(simulator);
    } else {
        send_packet(&ctx->stub, "E01");
        return;
    }

    encode_hex(response, value, GDB_REG_HEX_BYTES);
    response[GDB_REG_HEX_CHARS] = '\0';
    send_packet(&ctx->stub, response);
}

// Write single register (P command)
static void handle_write_single_register(gdb_context_t *ctx, void *simulator,
                                        const gdb_callbacks_t *callbacks) {
    char *packet = ctx->stub.packet_buffer + 1;
    char *equals = strchr(packet, '=');

    if (!equals) {
        send_packet(&ctx->stub, "E01");
        return;
    }

    *equals = '\0';
    int reg_num = (int)parse_hex(packet, equals - packet);
    gdb_reg_t value = parse_hex_le(equals + 1, (int)strlen(equals + 1));

    if (reg_num < 0 || reg_num > 32) {
        send_packet(&ctx->stub, "E01");
        return;
    }

    if (reg_num < 32) {
        callbacks->write_reg(simulator, reg_num, value);
    } else if (reg_num == 32) {
        callbacks->set_pc(simulator, value);
    } else {
        send_packet(&ctx->stub, "E01");
        return;
    }

    send_packet(&ctx->stub, "OK");
}

// Decode RSP binary payload (} escape and * run-length encoding)
static int decode_rsp_binary(const char *src, uint8_t *dst, uint32_t dst_len) {
    uint32_t di = 0;
    const char *p = src;

    while (di < dst_len && *p != '\0') {
        char c = *p++;
        if (c == '*') {
            if (di == 0 || *p == '\0') {
                return -1;
            }
            uint8_t count = (uint8_t)*p++;
            uint8_t prev = dst[di - 1];
            for (uint8_t i = 0; i < count && di < dst_len; i++) {
                dst[di++] = prev;
            }
        } else if (c == '}') {
            if (*p == '\0') {
                return -1;
            }
            dst[di++] = (uint8_t)(*p++ ^ 0x20);
        } else {
            dst[di++] = (uint8_t)c;
        }
    }

    return (di == dst_len) ? 0 : -1;
}

// Write memory with binary data (X command)
static void handle_write_memory_binary(gdb_context_t *ctx, void *simulator,
                                      const gdb_callbacks_t *callbacks) {
    char *packet = ctx->stub.packet_buffer + 1;
    char *comma = strchr(packet, ',');
    char *colon = strchr(packet, ':');

    if (!comma || !colon) {
        send_packet(&ctx->stub, "E01");
        return;
    }

    *comma = '\0';
    *colon = '\0';

    gdb_addr_t addr = parse_hex(packet, comma - packet);
    uint32_t len = (uint32_t)parse_hex(comma + 1, colon - comma - 1);
    char *data = colon + 1;

    if (len == 0 || len > GDB_BUFFER_SIZE) {
        send_packet(&ctx->stub, "E02");
        return;
    }

    uint8_t bytes[GDB_BUFFER_SIZE];
    if (decode_rsp_binary(data, bytes, len) < 0) {
        send_packet(&ctx->stub, "E03");
        return;
    }

    for (gdb_addr_t i = 0; i < len; i++) {
        callbacks->write_mem(simulator, addr + i, bytes[i], 1);
    }

    send_packet(&ctx->stub, "OK");
}

// Reset/restart target (R command)
static void handle_reset(gdb_context_t *ctx, void *simulator,
                        const gdb_callbacks_t *callbacks) {
    // Use simulator-specific reset if available
    if (callbacks->reset) {
        callbacks->reset(simulator);
    } else {
        // Default reset behavior
        // Reset PC to 0 (typical reset vector for RISC-V)
        callbacks->set_pc(simulator, 0);

        // Clear all registers (x1-x31, keep x0 as zero)
        for (int i = 1; i < 32; i++) {
            callbacks->write_reg(simulator, i, 0);
        }
    }

    // Clear breakpoints and watchpoints on reset
    gdb_stub_clear_breakpoints(ctx);
    gdb_stub_clear_watchpoints(ctx);

    ctx->should_stop = true;
    ctx->single_step = false;
    ctx->last_stop_signal = 5; // SIGTRAP
    ctx->breakpoint_hit = false;
    ctx->current_thread = 1;
    ctx->continue_thread = -1;
    ctx->stop_thread = 0;

    send_packet(&ctx->stub, "OK");
}

// Set thread for subsequent operations (H command)
static void handle_set_thread(gdb_context_t *ctx, void *simulator,
                             const gdb_callbacks_t *callbacks) {
    char *packet = ctx->stub.packet_buffer + 1;
    char op = packet[0];
    char *tid_str = packet + 1;
    int pid = 0;
    int tid = 0;
    int num_harts = callbacks->get_num_harts ? callbacks->get_num_harts(simulator) : 1;

    if (op != 'g' && op != 'c') {
        send_packet(&ctx->stub, "E01");
        return;
    }

    parse_thread_spec(tid_str, &pid, &tid);
    if (!thread_pid_valid(pid)) {
        send_packet(&ctx->stub, "E01");
        return;
    }

    if (op == 'g') {
        if (tid <= 0) {
            int stop_hart = callbacks->get_stop_hart ?
                callbacks->get_stop_hart(simulator) : 0;
            if (stop_hart < 0) {
                stop_hart = callbacks->get_focus_hart ?
                    callbacks->get_focus_hart(simulator) : 0;
            }
            tid = stop_hart + 1;
        }
        if (tid < 1 || tid > num_harts) {
            send_packet(&ctx->stub, "E01");
            return;
        }
        ctx->current_thread = tid;
        if (callbacks->set_focus_hart) {
            callbacks->set_focus_hart(simulator, tid - 1);
        }
    } else {
        ctx->continue_thread = resolve_continue_thread(pid, tid);
        if (ctx->continue_thread == -2) {
            send_packet(&ctx->stub, "E01");
            return;
        }
    }

    send_packet(&ctx->stub, "OK");
}

// Check if thread is alive (T command)
static void handle_thread_alive(gdb_context_t *ctx, void *simulator,
                               const gdb_callbacks_t *callbacks) {
    char *packet = ctx->stub.packet_buffer + 1;
    int pid = 0;
    int thread_id = 0;
    int num_harts = callbacks->get_num_harts ? callbacks->get_num_harts(simulator) : 1;

    parse_thread_spec(packet, &pid, &thread_id);
    if (!thread_pid_valid(pid)) {
        send_packet(&ctx->stub, "E01");
        return;
    }

    if (thread_id >= 1 && thread_id <= num_harts) {
        send_packet(&ctx->stub, "OK");
    } else {
        send_packet(&ctx->stub, "E01");
    }
}

// Enhanced halt reason reporting
static void handle_halt_reason(gdb_context_t *ctx, void *simulator,
                              const gdb_callbacks_t *callbacks) {
    char response[128];
    int tid = ctx->stop_thread ? ctx->stop_thread : ctx->current_thread;

    if (ctx->single_step) {
        format_stop_reply(ctx, response, sizeof(response), 5, tid, false, 0, 0);
    } else if (ctx->last_watchpoint_addr != 0) {
        format_stop_reply(ctx, response, sizeof(response), 5, tid, false,
                          ctx->last_watchpoint_addr, 0);
        ctx->last_watchpoint_addr = 0;
    } else {
        gdb_addr_t pc = callbacks->get_pc(simulator);
        if (gdb_stub_check_breakpoint(ctx, pc)) {
            format_stop_reply(ctx, response, sizeof(response), 5, tid, true, 0, 0);
        } else {
            format_stop_reply(ctx, response, sizeof(response), 5, tid, false, 0, 0);
        }
    }

    send_packet(&ctx->stub, response);
}

static void handle_vcont(gdb_context_t *ctx, void *simulator,
                         const gdb_callbacks_t *callbacks, int *run_cpu) {
    char *packet = ctx->stub.packet_buffer;

    if (strcmp(packet, "vCont?") == 0) {
        send_packet(&ctx->stub, "vCont;c;C; s;S");
        return;
    }

    if (strncmp(packet, "vCont", 5) != 0) {
        send_packet(&ctx->stub, "");
        return;
    }

    const char *actions = packet + 5;
    if (*actions == ';') {
        actions++;
    }
    if (*actions == '\0') {
        send_packet(&ctx->stub, "E01");
        return;
    }

    bool any_step = false;
    int step_tid = -1;
    int continue_tid = -1;
    bool have_action = false;

    while (*actions) {
        char action = *actions++;
        if (action == 'C' || action == 'S' || action == 'T') {
            if (isxdigit((unsigned char)actions[0]) &&
                isxdigit((unsigned char)actions[1])) {
                actions += 2;
            }
        }

        int pid = 0;
        int tid = -1;
        if (*actions == ':') {
            const char *spec = actions + 1;
            const char *next = spec;
            while (*next && *next != ';') {
                next++;
            }
            char spec_buf[32];
            size_t spec_len = (size_t)(next - spec);
            if (spec_len >= sizeof(spec_buf)) {
                send_packet(&ctx->stub, "E01");
                return;
            }
            memcpy(spec_buf, spec, spec_len);
            spec_buf[spec_len] = '\0';
            parse_thread_spec(spec_buf, &pid, &tid);
            actions = next;
        }

        if (!thread_pid_valid(pid)) {
            send_packet(&ctx->stub, "E01");
            return;
        }

        switch (action) {
        case 'c':
        case 'C': {
            int ct = resolve_continue_thread(pid, tid);
            if (ct == -2) {
                send_packet(&ctx->stub, "E01");
                return;
            }
            continue_tid = ct;
            have_action = true;
            break;
        }
        case 's':
        case 'S':
        case 't':
        case 'T': {
            int st = resolve_step_thread(ctx, pid, tid);
            if (st == -2) {
                send_packet(&ctx->stub, "E01");
                return;
            }
            any_step = true;
            step_tid = st;
            have_action = true;
            break;
        }
        default:
            send_packet(&ctx->stub, "");
            return;
        }

        if (*actions == ';') {
            actions++;
        }
    }

    if (!have_action) {
        send_packet(&ctx->stub, "E01");
        return;
    }

    if (any_step) {
        ctx->single_step = true;
        ctx->continue_thread = step_tid;
    } else {
        ctx->single_step = false;
        ctx->continue_thread = continue_tid;
    }

    ctx->should_stop = false;
    ctx->stop_thread = 0;
    if (callbacks->resume) {
        callbacks->resume(simulator);
    }
    *run_cpu = 1;
}

// Search memory for pattern (qSearch:memory command)
static void handle_search_memory(gdb_context_t *ctx, void *simulator,
                                const gdb_callbacks_t *callbacks) {
    char *packet = ctx->stub.packet_buffer + 15; // Skip "qSearch:memory:"
    char *colon1 = strchr(packet, ':');
    char *colon2 = colon1 ? strchr(colon1 + 1, ':') : NULL;

    if (!colon1 || !colon2) {
        send_packet(&ctx->stub, "E01");
        return;
    }

    *colon1 = '\0';
    *colon2 = '\0';

    gdb_addr_t start_addr = parse_hex(packet, colon1 - packet);
    gdb_addr_t search_len = parse_hex(colon1 + 1, colon2 - colon1 - 1);
    char *pattern = colon2 + 1;

    int pattern_len = strlen(pattern) / 2; // Hex encoded pattern

    if (pattern_len == 0 || (uint64_t)search_len < (uint64_t)pattern_len) {
        send_packet(&ctx->stub, "0");
        return;
    }

    // Simple linear search implementation
    for (gdb_addr_t addr = start_addr; addr <= start_addr + search_len - (gdb_addr_t)pattern_len; addr++) {
        bool match = true;
        for (int i = 0; i < pattern_len; i++) {
            uint8_t pattern_byte = (hex_to_int(pattern[i * 2]) << 4) | hex_to_int(pattern[i * 2 + 1]);
            uint8_t mem_byte = callbacks->read_mem(simulator, addr + i, 1) & 0xFF;
            if (pattern_byte != mem_byte) {
                match = false;
                break;
            }
        }
        if (match) {
            char response[48];
            snprintf(response, sizeof(response), "1," GDB_ADDR_HEX_FMT, addr);
            send_packet(&ctx->stub, response);
            return;
        }
    }

    send_packet(&ctx->stub, "0"); // Not found
}

// Process GDB commands
int gdb_stub_process(gdb_context_t *ctx, void *simulator,
                     const gdb_callbacks_t *callbacks) {
    if (!ctx->stub.connected) {
        return -1;
    }

    // Check for too many consecutive failures (DoS protection)
    if (ctx->stub.consecutive_failures >= 50) {
        fprintf(stderr, "GDB stub: Too many consecutive failures, disconnecting\n");
        return -1;
    }

    if (receive_packet(&ctx->stub) < 0) {
        return -1;
    }

    char cmd = ctx->stub.packet_buffer[0];

    switch (cmd) {
    case 0x03: // Ctrl-C (interrupt)
        ctx->should_stop = true;
        if (callbacks->halt_cpus) {
            callbacks->halt_cpus(simulator);
        }
        if (ctx->stop_thread == 0) {
            gdb_stub_set_stop_thread(ctx, 0);
        }
        gdb_stub_send_stop_reason(ctx, 2, 0); // SIGINT
        break;

    case '?': // Halt reason
        handle_halt_reason(ctx, simulator, callbacks);
        break;

    case 'q': // Query
        handle_query(ctx, simulator, callbacks);
        break;

    case 'Q': // General set
        handle_general_set(ctx, simulator, callbacks);
        break;

    case 'g': // Read registers
        handle_read_registers(ctx, simulator, callbacks);
        break;

    case 'G': // Write registers
        handle_write_registers(ctx, simulator, callbacks);
        break;

    case 'm': // Read memory
        handle_read_memory(ctx, simulator, callbacks);
        break;

    case 'M': // Write memory
        handle_write_memory(ctx, simulator, callbacks);
        break;

    case 'p': // Read single register
        handle_read_single_register(ctx, simulator, callbacks);
        break;

    case 'P': // Write single register
        handle_write_single_register(ctx, simulator, callbacks);
        break;

    case 'X': // Write memory (binary)
        handle_write_memory_binary(ctx, simulator, callbacks);
        break;

    case 'R': // Reset/restart
        handle_reset(ctx, simulator, callbacks);
        break;

    case 'H': // Set thread
        handle_set_thread(ctx, simulator, callbacks);
        break;

    case 'T': // Thread alive
        handle_thread_alive(ctx, simulator, callbacks);
        break;

    case 'v': // Extended commands (vCont, ...)
        if (strncmp(ctx->stub.packet_buffer, "vCont", 5) == 0) {
            int run_cpu = 0;
            handle_vcont(ctx, simulator, callbacks, &run_cpu);
            if (run_cpu) {
                return 1;
            }
        } else {
            send_packet(&ctx->stub, "");
        }
        break;

    case 'c': // Continue
        ctx->should_stop = false;
        ctx->single_step = false;
        ctx->stop_thread = 0;
        ctx->continue_thread = -1;
        if (callbacks->resume) {
            callbacks->resume(simulator);
        }
        return 1;

    case 's': // Single step
        ctx->should_stop = false;
        ctx->single_step = true;
        ctx->stop_thread = 0;
        if (ctx->continue_thread < 0) {
            ctx->continue_thread = ctx->current_thread;
        }
        if (callbacks->resume) {
            callbacks->resume(simulator);
        }
        return 1;

    case 'Z': // Insert breakpoint
        handle_breakpoint(ctx, true);
        break;

    case 'z': // Remove breakpoint
        handle_breakpoint(ctx, false);
        break;

    case 'k': // Kill
        return -1;
        break;

    case 'D': // Detach
        send_packet(&ctx->stub, "OK");
        ctx->stub.connected = false;
        return -1;
        break;

    default:
        send_packet(&ctx->stub, ""); // Not supported
        break;
    }

    return 0;
}

// Breakpoint management
int gdb_stub_add_breakpoint(gdb_context_t *ctx, gdb_addr_t addr) {
    if (ctx->breakpoint_count >= MAX_BREAKPOINTS) {
        return -1;
    }

    // Check if already exists
    for (int i = 0; i < ctx->breakpoint_count; i++) {
        if (ctx->breakpoints[i].addr == addr) {
            ctx->breakpoints[i].enabled = true;
            return 0;
        }
    }

    ctx->breakpoints[ctx->breakpoint_count].addr = addr;
    ctx->breakpoints[ctx->breakpoint_count].enabled = true;
    ctx->breakpoint_count++;
    return 0;
}

int gdb_stub_remove_breakpoint(gdb_context_t *ctx, gdb_addr_t addr) {
    for (int i = 0; i < ctx->breakpoint_count; i++) {
        if (ctx->breakpoints[i].addr == addr) {
            ctx->breakpoints[i].enabled = false;
            return 0;
        }
    }
    return -1;
}

void gdb_stub_clear_breakpoints(gdb_context_t *ctx) {
    ctx->breakpoint_count = 0;
}

bool gdb_stub_check_breakpoint(gdb_context_t *ctx, gdb_addr_t pc) {
    for (int i = 0; i < ctx->breakpoint_count; i++) {
        if (ctx->breakpoints[i].enabled && ctx->breakpoints[i].addr == pc) {
            ctx->breakpoint_hit = true;
            return true;
        }
    }
    return false;
}

// Watchpoint management
int gdb_stub_add_watchpoint(gdb_context_t *ctx, gdb_addr_t addr, gdb_addr_t len, watchpoint_type_t type) {
    if (len == 0) {
        len = 4;
    }
    if (ctx->watchpoint_count >= MAX_WATCHPOINTS) {
        return -1;
    }

    // Check if already exists
    for (int i = 0; i < ctx->watchpoint_count; i++) {
        if (ctx->watchpoints[i].addr == addr &&
            ctx->watchpoints[i].len == len &&
            ctx->watchpoints[i].type == type) {
            ctx->watchpoints[i].enabled = true;
            return 0;
        }
    }

    ctx->watchpoints[ctx->watchpoint_count].addr = addr;
    ctx->watchpoints[ctx->watchpoint_count].len = len;
    ctx->watchpoints[ctx->watchpoint_count].type = type;
    ctx->watchpoints[ctx->watchpoint_count].enabled = true;
    ctx->watchpoint_count++;
    return 0;
}

int gdb_stub_remove_watchpoint(gdb_context_t *ctx, gdb_addr_t addr, gdb_addr_t len, watchpoint_type_t type) {
    for (int i = 0; i < ctx->watchpoint_count; i++) {
        if (ctx->watchpoints[i].addr == addr &&
            ctx->watchpoints[i].len == len &&
            ctx->watchpoints[i].type == type) {
            ctx->watchpoints[i].enabled = false;
            return 0;
        }
    }
    return -1;
}

void gdb_stub_clear_watchpoints(gdb_context_t *ctx) {
    ctx->watchpoint_count = 0;
}

// Check if memory read triggers a watchpoint
bool gdb_stub_check_watchpoint_read(gdb_context_t *ctx, gdb_addr_t addr, gdb_addr_t len) {
    for (int i = 0; i < ctx->watchpoint_count; i++) {
        if (!ctx->watchpoints[i].enabled) continue;

        watchpoint_t *wp = &ctx->watchpoints[i];
        if (wp->type != WATCHPOINT_READ && wp->type != WATCHPOINT_ACCESS) continue;

        if (ranges_overlap(addr, len, wp->addr, wp->len)) {
            ctx->last_watchpoint_addr = wp->addr;
            return true;
        }
    }
    return false;
}

// Check if memory write triggers a watchpoint
bool gdb_stub_check_watchpoint_write(gdb_context_t *ctx, gdb_addr_t addr, gdb_addr_t len) {
    for (int i = 0; i < ctx->watchpoint_count; i++) {
        if (!ctx->watchpoints[i].enabled) continue;

        watchpoint_t *wp = &ctx->watchpoints[i];
        if (wp->type != WATCHPOINT_WRITE && wp->type != WATCHPOINT_ACCESS) continue;

        if (ranges_overlap(addr, len, wp->addr, wp->len)) {
            ctx->last_watchpoint_addr = wp->addr;
            return true;
        }
    }
    return false;
}

void gdb_stub_close(gdb_context_t *ctx) {
    if (ctx->stub.client_fd >= 0) {
        close(ctx->stub.client_fd);
        ctx->stub.client_fd = -1;
    }
    if (ctx->stub.socket_fd >= 0) {
        close(ctx->stub.socket_fd);
        ctx->stub.socket_fd = -1;
    }
    ctx->stub.connected = false;
    ctx->stub.enabled = false;
}

int gdb_stub_send_stop_signal(gdb_context_t *ctx, int signal) {
    return gdb_stub_send_stop_reason(ctx, signal, 0);
}

void gdb_stub_set_stop_thread(gdb_context_t *ctx, int thread_id) {
    if (thread_id >= 1) {
        ctx->stop_thread = thread_id;
    } else if (ctx->current_thread >= 1) {
        ctx->stop_thread = ctx->current_thread;
    } else {
        ctx->stop_thread = 1;
    }
}

bool gdb_stub_should_run_thread(gdb_context_t *ctx, int thread_id) {
    if (ctx->continue_thread < 0) {
        return true;
    }
    return ctx->continue_thread == thread_id;
}

int gdb_stub_send_stop_reason(gdb_context_t *ctx, int signal, gdb_addr_t addr) {
    char response[128];
    int tid = ctx->stop_thread ? ctx->stop_thread : ctx->current_thread;

    if (ctx->breakpoint_hit) {
        format_stop_reply(ctx, response, sizeof(response), signal, tid, true, 0, 0);
        ctx->breakpoint_hit = false;
    } else if (ctx->last_watchpoint_addr != 0) {
        format_stop_reply(ctx, response, sizeof(response), signal, tid, false,
                          ctx->last_watchpoint_addr, 0);
        ctx->last_watchpoint_addr = 0;
    } else if (addr != 0) {
        format_stop_reply(ctx, response, sizeof(response), signal, tid, false, 0, addr);
    } else {
        format_stop_reply(ctx, response, sizeof(response), signal, tid, false, 0, 0);
    }

    return send_packet(&ctx->stub, response);
}
