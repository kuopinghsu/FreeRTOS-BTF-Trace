// ============================================================================
// File: sim/gdb_stub.h
// Project: FreeRTOS-RISCV-SMP
// Description: GDB Remote Serial Protocol stub — public interface.
//
// Provides the C API used by the simulator to accept GDB connections and
// service register read/write, memory read/write, and step/continue requests.
// ============================================================================

#ifndef GDB_STUB_H
#define GDB_STUB_H

#include <stdint.h>
#include <stdbool.h>

#define GDB_BUFFER_SIZE 4096

#if defined( GDB_STUB_RISCV32 ) && defined( GDB_STUB_RISCV64 )
    #error "Define only one of GDB_STUB_RISCV32 or GDB_STUB_RISCV64"
#elif defined( GDB_STUB_RISCV32 )
    #define GDB_STUB_XLEN 32
    typedef uint32_t gdb_reg_t;
    typedef uint32_t gdb_addr_t;
#elif defined( GDB_STUB_RISCV64 )
    #define GDB_STUB_XLEN 64
    typedef uint64_t gdb_reg_t;
    typedef uint64_t gdb_addr_t;
#elif defined( __riscv_xlen ) && ( __riscv_xlen == 32 )
    #define GDB_STUB_XLEN 32
    typedef uint32_t gdb_reg_t;
    typedef uint32_t gdb_addr_t;
#elif defined( __riscv_xlen ) && ( __riscv_xlen == 64 )
    #define GDB_STUB_XLEN 64
    typedef uint64_t gdb_reg_t;
    typedef uint64_t gdb_addr_t;
#else
    #define GDB_STUB_XLEN 64
    typedef uint64_t gdb_reg_t;
    typedef uint64_t gdb_addr_t;
#endif

// GDB stub state
typedef struct {
    int socket_fd;
    int client_fd;
    uint16_t port;
    bool connected;
    bool enabled;
    bool no_ack_mode;           // QStartNoAckMode enabled
    int consecutive_failures;   // Track failures for DoS protection
    char packet_buffer[GDB_BUFFER_SIZE];
    int packet_size;
} gdb_stub_t;

// Breakpoint management
typedef struct {
    gdb_addr_t addr;
    bool enabled;
} breakpoint_t;

// Watchpoint types
typedef enum {
    WATCHPOINT_WRITE = 2,  // Z2: write watchpoint
    WATCHPOINT_READ = 3,   // Z3: read watchpoint
    WATCHPOINT_ACCESS = 4  // Z4: access (read+write) watchpoint
} watchpoint_type_t;

// Watchpoint management
typedef struct {
    gdb_addr_t addr;
    gdb_addr_t len;
    watchpoint_type_t type;
    bool enabled;
} watchpoint_t;

#define MAX_BREAKPOINTS 64
#define MAX_WATCHPOINTS 32

// GDB stub interface
typedef struct {
    gdb_stub_t stub;
    breakpoint_t breakpoints[MAX_BREAKPOINTS];
    int breakpoint_count;
    watchpoint_t watchpoints[MAX_WATCHPOINTS];
    int watchpoint_count;
    bool single_step;
    bool should_stop;
    gdb_addr_t last_watchpoint_addr;  // Address of last hit watchpoint
    int last_stop_signal;           // Last stop signal sent
    bool breakpoint_hit;            // Flag indicating breakpoint was hit
    /* SMP thread state (GDB thread ids are 1-based hart ids). */
    int current_thread;             // Selected thread for register ops
    int continue_thread;            // -1 = all harts, else 1-based thread id
    int stop_thread;                // Thread that caused the last stop (1-based)
    bool multiprocess_active;       // Client negotiated multiprocess+ via qSupported
} gdb_context_t;

// Callback functions for simulator access
typedef struct {
    gdb_reg_t (*read_reg)(void *sim, int reg_num);
    void (*write_reg)(void *sim, int reg_num, gdb_reg_t value);
    gdb_reg_t (*read_mem)(void *sim, gdb_addr_t addr, int size);
    void (*write_mem)(void *sim, gdb_addr_t addr, gdb_reg_t value, int size);
    gdb_addr_t (*get_pc)(void *sim);
    void (*set_pc)(void *sim, gdb_addr_t pc);
    void (*single_step)(void *sim);
    bool (*is_running)(void *sim);
    void (*reset)(void *sim);
    void (*resume)(void *sim);
    int (*get_num_harts)(void *sim);
    void (*set_focus_hart)(void *sim, int hart);
    int (*get_focus_hart)(void *sim);
    int (*get_stop_hart)(void *sim);
    void (*halt_cpus)(void *sim);
} gdb_callbacks_t;

#ifdef __cplusplus
extern "C" {
#endif

// Initialize GDB stub
int gdb_stub_init(gdb_context_t *ctx, uint16_t port);

// Accept client connection
int gdb_stub_accept(gdb_context_t *ctx);

// Process GDB commands
int gdb_stub_process(gdb_context_t *ctx, void *simulator,
                     const gdb_callbacks_t *callbacks);

// Check if should stop at current PC
bool gdb_stub_check_breakpoint(gdb_context_t *ctx, gdb_addr_t pc);

// Close GDB stub
void gdb_stub_close(gdb_context_t *ctx);

// Helper functions
int gdb_stub_add_breakpoint(gdb_context_t *ctx, gdb_addr_t addr);
int gdb_stub_remove_breakpoint(gdb_context_t *ctx, gdb_addr_t addr);
void gdb_stub_clear_breakpoints(gdb_context_t *ctx);

// Watchpoint functions
int gdb_stub_add_watchpoint(gdb_context_t *ctx, gdb_addr_t addr, gdb_addr_t len, watchpoint_type_t type);
int gdb_stub_remove_watchpoint(gdb_context_t *ctx, gdb_addr_t addr, gdb_addr_t len, watchpoint_type_t type);
bool gdb_stub_check_watchpoint_read(gdb_context_t *ctx, gdb_addr_t addr, gdb_addr_t len);
bool gdb_stub_check_watchpoint_write(gdb_context_t *ctx, gdb_addr_t addr, gdb_addr_t len);
void gdb_stub_clear_watchpoints(gdb_context_t *ctx);

// Send stop signal to GDB
int gdb_stub_send_stop_signal(gdb_context_t *ctx, int signal);

// Enhanced stop reason reporting
int gdb_stub_send_stop_reason(gdb_context_t *ctx, int signal, gdb_addr_t addr);

// Record which thread (1-based hart id) caused a stop
void gdb_stub_set_stop_thread(gdb_context_t *ctx, int thread_id);

// True if continue/step should run the given thread (continue_thread == -1 means all)
bool gdb_stub_should_run_thread(gdb_context_t *ctx, int thread_id);

#ifdef __cplusplus
}
#endif

#endif // GDB_STUB_H
