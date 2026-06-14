// ============================================================================
// File: sim/simulator.h
// Project: FreeRTOS-RISCV-SMP
// Description: Public interface for the RV64IMAC software simulator.
//
// Declares the Simulator class, configuration Options struct, and supporting
// types.  Consumers should include this header and link against simulator.cpp.
// ============================================================================

#ifndef RISCV64_SIMULATOR_H
#define RISCV64_SIMULATOR_H

#include <array>
#include <cstdint>
#include <deque>
#include <cstdio>
#include <map>
#include <optional>
#include <sys/stat.h>
#include <set>
#include <stdexcept>
#include <string>
#include <unordered_map>
#include <vector>

#include "gdb_stub.h"

namespace sim {

using HostStat = struct stat;

constexpr uint64_t kDefaultRamBase = 0x80000000ull;
constexpr uint64_t kDefaultRamSize = 128ull * 1024ull * 1024ull;
constexpr uint64_t kClintBase = 0x02000000ull;
constexpr uint64_t kMtimeBase = kClintBase + 0xBFF8ull;
constexpr uint64_t kMtimecmpBase = kClintBase + 0x4000ull;
constexpr uint64_t kPageSize = 4096ull;
constexpr int kMaxHarts = 16;

struct Options {
    int cores = 1;
    uint64_t ram_base = kDefaultRamBase;
    uint64_t ram_size = kDefaultRamSize;
    uint16_t gdb_port = 0;
    uint64_t max_instructions = 0;
    bool trace = false;
    std::string elf_path;
    std::vector<std::string> target_args;
    // RISC-V arch-test signature options
    std::string test_signature;          // path for --test-signature=<file>
    uint32_t signature_granularity = 4;  // bytes per signature word (default 4)
    bool stats = true;                   // print simulation stats on exit
};

struct RunStats {
    uint64_t insns_retired  = 0;  // total instructions retired across all harts
    uint64_t cycles         = 0;  // CLINT mtime (global clock ticks, not insns retired)
    double   wall_seconds   = 0.0;
    double   sim_hz() const {
        return wall_seconds > 0.0 ? static_cast<double>(insns_retired) / wall_seconds : 0.0;
    }
};

class Trap : public std::runtime_error {
public:
    Trap(uint64_t cause, uint64_t tval, const std::string &what_arg);

    uint64_t cause() const noexcept;
    uint64_t tval() const noexcept;

private:
    uint64_t cause_;
    uint64_t tval_;
};

class ExitRequest : public std::runtime_error {
public:
    explicit ExitRequest(int code);

    int code() const noexcept;

private:
    int code_;
};

struct HartState {
    std::array<uint64_t, 32> regs{};
    uint64_t pc = 0;

    /* ── Standard M-mode CSRs (0x3xx) ──────────────────────────────── */
    uint64_t mstatus = 0;
    uint64_t misa = 0;
    uint64_t mie = 0;
    uint64_t mip = 0;       /* hardware-driven; MTIP/MSIP set by CLINT */
    uint64_t mtvec = 0;
    uint64_t mcounteren = 0;
    uint64_t menvcfg = 0;
    uint64_t mcountinhibit = 0;
    uint64_t medeleg = 0;         /* WARL: exception delegation (legal mask 0x00fcb7fe) */
    uint64_t mideleg = 0x1444;    /* WARL: interrupt delegation; bits 2,6,10,12 hardwired-1 */
    std::array<uint64_t, 29> mhpmevent{};    /* mhpmevent3..31  [0..28] */
    uint64_t mscratch = 0;
    uint64_t mepc = 0;
    uint64_t mcause = 0;
    uint64_t mtval = 0;

    /* ── S-mode CSRs needed for sret / sepc tests (0x1xx) ───────────── */
    uint64_t sepc = 0;

    /* ── M-mode performance counters (0xBxx) ────────────────────────── */
    uint64_t mcycle = 0;
    uint64_t minstret = 0;
    std::array<uint64_t, 29> mhpmcounter{};  /* mhpmcounter3..31 [0..28] */

    /* ── Hart control ───────────────────────────────────────────────── */
    uint64_t reservation = UINT64_MAX;
    bool reservation_valid = false;
    bool waiting_for_interrupt = false;
    bool halted = false;
    bool single_step = false;
    uint32_t priv_mode = 3; /* current privilege mode: 3=M, 1=S, 0=U */
};

class Simulator {
public:
    explicit Simulator(const Options &options);

    void load_elf(const std::string &path);
    void reset();
    RunStats run();
    bool step_hart(int hart_id);
    void dump_signature(const std::string &path, uint32_t granularity) const;

    uint64_t read_reg(int hart_id, int reg_num) const;
    void write_reg(int hart_id, int reg_num, uint64_t value);
    uint64_t read_memory(uint64_t addr, unsigned size, bool exec = false);
    void write_memory(uint64_t addr, uint64_t value, unsigned size);
    uint64_t get_pc(int hart_id) const;
    void set_pc(int hart_id, uint64_t pc);
    int core_count() const;
    int focus_hart() const;
    void set_focus_hart(int hart_id);
    int stop_hart() const;
    bool is_running() const;
    void resume_all();
    void halt_all();
    void request_single_step(int hart_id);
    int exit_code() const;
    bool has_exited() const;

    int poll_gdb(gdb_context_t *ctx);

private:
    struct Page {
        std::array<uint8_t, kPageSize> bytes{};
    };

    struct PendingFromHost {
        uint64_t value = 0;
    };

    struct RiscvStat {
        uint64_t dev = 0;
        uint64_t ino = 0;
        uint32_t mode = 0;
        uint32_t nlink = 0;
        uint32_t uid = 0;
        uint32_t gid = 0;
        uint64_t rdev = 0;
        uint64_t pad1 = 0;
        uint64_t size = 0;
        uint32_t blksize = 0;
        uint32_t pad2 = 0;
        uint64_t blocks = 0;
        uint64_t atime = 0;
        uint64_t pad3 = 0;
        uint64_t mtime = 0;
        uint64_t pad4 = 0;
        uint64_t ctime = 0;
        uint64_t pad5 = 0;
        uint32_t unused4 = 0;
        uint32_t unused5 = 0;
    };

    static constexpr uint64_t kMstatusMie = 1ull << 3;
    static constexpr uint64_t kMieMsip = 1ull << 3;
    static constexpr uint64_t kMieMtip = 1ull << 7;
    static constexpr uint64_t kMipMsip = 1ull << 3;
    static constexpr uint64_t kMipMtip = 1ull << 7;
    /* mstatus writable bits — matched to spike (rv64imafdcbvh + Zicfilp).
     * UXL/SXL (33:32, 35:34) and MBE/SBE (37:36) are hardwired and excluded. */
    static constexpr uint64_t kMstatusWriteMask =
        (1ull <<  1) |               // SIE
        (1ull <<  3) |               // MIE
        (1ull <<  5) |               // SPIE
        (1ull <<  6) |               // UBE
        (1ull <<  7) |               // MPIE
        (1ull <<  8) |               // SPP
        (3ull <<  9) |               // VS[1:0]
        (3ull << 11) |               // MPP[1:0]
        (3ull << 13) |               // FS[1:0]
        // XS[1:0] (15:16) is read-only: computed from FS/VS on read
        (1ull << 17) |               // MPRV
        (1ull << 18) |               // SUM
        (1ull << 19) |               // MXR
        (1ull << 20) |               // TVM
        (1ull << 21) |               // TW
        (1ull << 22) |               // TSR
        (1ull << 23) |               // SPELP (Zicfilp S-mode effective landing pad)
        (1ull << 38) |               // GVA   (H extension guest virtual address)
        (1ull << 39) |               // MPV   (H extension machine previous virtualization)
        (1ull << 41);                // MPELP (Zicfilp machine previous effective landing pad)
    static constexpr uint64_t kMisaValue =
        (2ull << 62) |
        (1ull << ('A' - 'A')) |
        (1ull << ('C' - 'A')) |
        (1ull << ('I' - 'A')) |
        (1ull << ('M' - 'A'));

    const Options options_;
    std::vector<HartState> harts_;
    // Flat byte array covering the entire RAM region — eliminates hash-map
    // lookups from the hot path.  Out-of-RAM accesses still fall back to pages_.
    std::vector<uint8_t> flat_ram_;
    std::unordered_map<uint64_t, Page> pages_;
    std::map<std::string, uint64_t> symbols_;
    std::set<uint64_t> loaded_pages_;
    uint64_t entry_point_ = 0;
    uint64_t tohost_addr_ = 0;
    uint64_t fromhost_addr_ = 0;
    uint64_t mtime_ = 0;
    std::array<uint64_t, kMaxHarts> mtimecmp_{};
    std::deque<uint64_t> fromhost_queue_;
    int focus_hart_ = 0;
    int stop_hart_ = 0;
    bool running_ = true;
    bool exit_requested_ = false;
    bool htif_tohost_dirty_ = false;  // set when test writes a non-zero value to tohost
    int exit_code_ = 0;
    int stdin_flags_ = -1;

    struct CommitEntry {
        enum class Kind : uint8_t { Reg, MemR, MemW, Csr } kind;
        uint32_t num;    // register index (0–31) or CSR address
        uint64_t addr;   // memory address (MemR/MemW)
        uint64_t val;    // new value (or loaded/stored value)
        uint64_t oval;   // CSR old value
    };
    std::vector<CommitEntry> commit_log_;   // populated during step_internal when trace enabled

    void ensure_page(uint64_t addr);
    Page *find_page(uint64_t addr);
    const Page *find_page(uint64_t addr) const;
    uint8_t load8(uint64_t addr, bool exec = false);
    uint16_t load16(uint64_t addr, bool exec = false);
    uint32_t load32(uint64_t addr, bool exec = false);
    uint64_t load64(uint64_t addr, bool exec = false);
    void store8(uint64_t addr, uint8_t value);
    void store16(uint64_t addr, uint16_t value);
    void store32(uint64_t addr, uint32_t value);
    void store64(uint64_t addr, uint64_t value);

    bool read_mmio(uint64_t addr, unsigned size, uint64_t &value);
    bool write_mmio(uint64_t addr, uint64_t value, unsigned size);
    void write_blob(uint64_t addr, const void *data, size_t len);
    void zero_fill(uint64_t addr, size_t len);
    void load_symbols_from_elf(const std::vector<uint8_t> &image, uint64_t shoff,
                               uint16_t shentsize, uint16_t shnum, uint16_t shstrndx);

    void service_htif();
    void queue_fromhost(uint64_t value);
    void try_deliver_fromhost();
    void handle_htif_command(uint64_t value);
    void handle_htif_console(uint8_t cmd, uint64_t payload);
    void handle_htif_syscall(uint64_t payload);
    void complete_htif_request(uint8_t dev, uint8_t cmd, uint64_t payload);
    void set_exit_code(int code);
    int host_openat(int dirfd, const std::string &path, int flags, int mode) const;
    int host_dirfd(int dirfd) const;
    std::string read_c_string(uint64_t addr, uint64_t len_hint = 0);
    void write_stat(uint64_t addr, const HostStat &host_stat);
    void write_mainvars(uint64_t addr, uint64_t limit);
    void dump_all_hart_registers(FILE *out) const;

    void tick();  // advance global mtime_ by one clock tick; refresh MTIP on all harts
    void step_internal(int hart_id);
    void execute_trap(int hart_id, const Trap &trap, uint64_t trap_pc, bool advance_pc);
    bool handle_interrupt(int hart_id);
    bool should_wake_from_wfi(const HartState &hart) const;
    uint32_t fetch_insn32(int hart_id, bool &compressed);
    uint32_t decompress(uint16_t insn) const;
    void execute32(int hart_id, uint32_t insn, bool compressed);

    uint64_t csr_read(HartState &hart, uint32_t csr) const;
    void csr_write(HartState &hart, uint32_t csr, uint64_t value);
    uint64_t amo_op(uint32_t funct5, uint64_t lhs, uint64_t rhs, bool word) const;
    static uint64_t sign_extend(uint64_t value, unsigned bits);
    static uint64_t mask_for_size(unsigned size);
    static int64_t arithmetic_shift_right(int64_t value, unsigned shamt);
    static uint64_t load_u(const std::vector<uint8_t> &buf, size_t offset, size_t size);
};

} // namespace sim

#endif