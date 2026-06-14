// ============================================================================
// File: sim/simulator.cpp
// Project: FreeRTOS-RISCV-SMP
// Description: RV64IMAC + Zicsr software simulator implementation.
//
// Interprets RISC-V ELF binaries cycle-by-cycle.  Supports:
//   - RV64IMAC base ISA (integer, multiply/divide, atomics, compressed)
//   - Machine-mode CSRs, timer interrupts (CLINT), and WFI
//   - HTIF (Host-Target Interface) for tohost/fromhost communication
//   - Proxy kernel syscall emulation via HTIF syscall device
//   - GDB Remote Serial Protocol stub for source-level debugging
//   - RISC-V arch-test signature dump (--test-signature)
//   - Instruction-level trace with disassembly (--trace)
//
// Memory map:
//   0x02000000  CLINT (mtime/mtimecmp — global fixed-rate clock, not per-insn)
//   0x80000000  RAM base (default 128 MB)
//   0x83FFF000  HTIF tohost/fromhost (arch-test ELFs)
// ============================================================================

#include "simulator.h"
#include "riscv-dis.h"

#include "elf.h"
#include <errno.h>
#include <fcntl.h>
#include <signal.h>
#include <sys/stat.h>
#include <sys/types.h>
#include <unistd.h>

#include <algorithm>
#include <array>
#include <chrono>
#include <cinttypes>
#include <cstdio>
#include <cstring>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <limits>
#include <sstream>

namespace sim {

namespace {

volatile sig_atomic_t g_sigint_requested = 0;

void on_sigint(int) {
    g_sigint_requested = 1;
}

constexpr uint64_t kInsnAccessFault = 1;
constexpr uint64_t kIllegalInstruction = 2;
constexpr uint64_t kBreakpoint = 3;
constexpr uint64_t kMachineSoftwareInterrupt = (1ull << 63) | 3ull;
constexpr uint64_t kLoadAddrMisaligned = 4;
constexpr uint64_t kLoadAccessFault = 5;
constexpr uint64_t kStoreAddrMisaligned = 6;
constexpr uint64_t kStoreAccessFault = 7;
constexpr uint64_t kEcallFromMmode = 11;
constexpr uint64_t kMachineTimerInterrupt = (1ull << 63) | 7ull;

constexpr uint64_t kHtifDevSyscall = 0;
constexpr uint64_t kHtifDevConsole = 1;

constexpr uint64_t kSysGetcwd = 17;
constexpr uint64_t kSysFcntl = 25;
constexpr uint64_t kSysMkdirat = 34;
constexpr uint64_t kSysUnlinkat = 35;
constexpr uint64_t kSysLinkat = 37;
constexpr uint64_t kSysRenameat = 38;
constexpr uint64_t kSysFaccessat = 48;
constexpr uint64_t kSysChdir = 49;
constexpr uint64_t kSysOpenat = 56;
constexpr uint64_t kSysClose = 57;
constexpr uint64_t kSysLseek = 62;
constexpr uint64_t kSysRead = 63;
constexpr uint64_t kSysWrite = 64;
constexpr uint64_t kSysReadv = 65;
constexpr uint64_t kSysWritev = 66;
constexpr uint64_t kSysPread = 67;
constexpr uint64_t kSysPwrite = 68;
constexpr uint64_t kSysReadlinkat = 78;
constexpr uint64_t kSysFstatat = 79;
constexpr uint64_t kSysFstat = 80;
constexpr uint64_t kSysExit = 93;
constexpr uint64_t kSysGetmainvars = 2011;

constexpr int kAtFdcwd = -100;

uint64_t bits(uint32_t insn, int hi, int lo) {
    return (insn >> lo) & ((1u << (hi - lo + 1)) - 1u);
}

int64_t sext(uint64_t value, int bits_count) {
    uint64_t shift = 64 - static_cast<unsigned>(bits_count);
    return static_cast<int64_t>(static_cast<int64_t>(value << shift) >> shift);
}

uint64_t encode_rvc_j_imm(uint16_t insn) {
    uint64_t imm = 0;
    imm |= ((insn >> 12) & 0x1) << 11;
    imm |= ((insn >> 11) & 0x1) << 4;
    imm |= ((insn >> 9) & 0x3) << 8;
    imm |= ((insn >> 8) & 0x1) << 10;
    imm |= ((insn >> 7) & 0x1) << 6;
    imm |= ((insn >> 6) & 0x1) << 7;
    imm |= ((insn >> 3) & 0x7) << 1;
    imm |= ((insn >> 2) & 0x1) << 5;
    return static_cast<uint64_t>(sext(imm, 12));
}

uint64_t encode_rvc_b_imm(uint16_t insn) {
    uint64_t imm = 0;
    imm |= ((insn >> 12) & 0x1) << 8;
    imm |= ((insn >> 10) & 0x3) << 3;
    imm |= ((insn >> 5) & 0x3) << 6;
    imm |= ((insn >> 3) & 0x3) << 1;
    imm |= ((insn >> 2) & 0x1) << 5;
    return static_cast<uint64_t>(sext(imm, 9));
}

uint64_t encode_i_imm(uint32_t insn) {
    return static_cast<uint64_t>(sext(bits(insn, 31, 20), 12));
}

uint64_t encode_s_imm(uint32_t insn) {
    return static_cast<uint64_t>(sext((bits(insn, 31, 25) << 5) | bits(insn, 11, 7), 12));
}

uint64_t encode_b_imm(uint32_t insn) {
    uint64_t imm = 0;
    imm |= bits(insn, 31, 31) << 12;
    imm |= bits(insn, 7, 7) << 11;
    imm |= bits(insn, 30, 25) << 5;
    imm |= bits(insn, 11, 8) << 1;
    return static_cast<uint64_t>(sext(imm, 13));
}

uint64_t encode_u_imm(uint32_t insn) {
    /* U-type immediate is sign-extended to 64 bits in RV64 (RISC-V spec vol. I, §2.3). */
    return static_cast<uint64_t>(static_cast<int32_t>(insn & 0xFFFFF000u));
}

uint64_t encode_j_imm(uint32_t insn) {
    uint64_t imm = 0;
    imm |= bits(insn, 31, 31) << 20;
    imm |= bits(insn, 19, 12) << 12;
    imm |= bits(insn, 20, 20) << 11;
    imm |= bits(insn, 30, 21) << 1;
    return static_cast<uint64_t>(sext(imm, 21));
}

uint32_t encode_jal(uint32_t rd, uint64_t imm) {
    uint32_t uimm = static_cast<uint32_t>(imm);
    return (((uimm >> 20) & 0x1) << 31) |
           (((uimm >> 1) & 0x3FF) << 21) |
           (((uimm >> 11) & 0x1) << 20) |
           (((uimm >> 12) & 0xFF) << 12) |
           (rd << 7) |
           0x6F;
}

uint64_t mulhu_u64(uint64_t lhs, uint64_t rhs) {
    __extension__ unsigned __int128 product =
        static_cast<unsigned __int128>(lhs) * static_cast<unsigned __int128>(rhs);
    return static_cast<uint64_t>(product >> 64);
}

std::vector<uint8_t> read_file(const std::string &path) {
    std::ifstream input(path, std::ios::binary);
    if (!input) {
        throw std::runtime_error("unable to open ELF: " + path);
    }
    return std::vector<uint8_t>(std::istreambuf_iterator<char>(input), std::istreambuf_iterator<char>());
}

// ABI register names (x0–x31) used in the commit log to match disassembly.
static constexpr const char *kRegAbiNames[32] = {
    "zero", "ra",  "sp",  "gp",  "tp",  "t0",  "t1",  "t2",
    "s0",   "s1",  "a0",  "a1",  "a2",  "a3",  "a4",  "a5",
    "a6",   "a7",  "s2",  "s3",  "s4",  "s5",  "s6",  "s7",
    "s8",   "s9",  "s10", "s11", "t3",  "t4",  "t5",  "t6",
};

// Map a CSR address to its canonical name for the commit log; returns nullptr
// for unknown CSR numbers (callers should fall back to "0x%03x").
const char *csr_name_for_log(uint32_t csr) {
    switch (csr) {
    case 0x100: return "sstatus";
    case 0x104: return "sie";
    case 0x105: return "stvec";
    case 0x106: return "scounteren";
    case 0x140: return "sscratch";
    case 0x141: return "sepc";
    case 0x142: return "scause";
    case 0x143: return "stval";
    case 0x144: return "sip";
    case 0x300: return "mstatus";
    case 0x301: return "misa";
    case 0x302: return "medeleg";
    case 0x303: return "mideleg";
    case 0x304: return "mie";
    case 0x305: return "mtvec";
    case 0x306: return "mcounteren";
    case 0x30A: return "menvcfg";
    case 0x320: return "mcountinhibit";
    case 0x340: return "mscratch";
    case 0x341: return "mepc";
    case 0x342: return "mcause";
    case 0x343: return "mtval";
    case 0x344: return "mip";
    case 0xB00: return "mcycle";
    case 0xB02: return "minstret";
    case 0xC00: return "cycle";
    case 0xC01: return "time";
    case 0xC02: return "instret";
    case 0xF11: return "mvendorid";
    case 0xF12: return "marchid";
    case 0xF13: return "mimpid";
    case 0xF14: return "mhartid";
    case 0xF15: return "mconfigptr";
    default:    return nullptr;
    }
}

} // namespace

Trap::Trap(uint64_t cause, uint64_t tval, const std::string &what_arg)
    : std::runtime_error(what_arg), cause_(cause), tval_(tval) {}

uint64_t Trap::cause() const noexcept { return cause_; }
uint64_t Trap::tval() const noexcept { return tval_; }

ExitRequest::ExitRequest(int code) : std::runtime_error("exit"), code_(code) {}
int ExitRequest::code() const noexcept { return code_; }

Simulator::Simulator(const Options &options)
    : options_(options), harts_(static_cast<size_t>(options.cores)),
      flat_ram_(options.ram_size, 0) {
    for (int hart = 0; hart < options_.cores; ++hart) {
        harts_[hart].misa = kMisaValue;
        harts_[hart].regs.fill(0);
        harts_[hart].regs[2] = options_.ram_base + options_.ram_size - (hart * 0x10000ull) - 16;
        mtimecmp_[hart] = std::numeric_limits<uint64_t>::max();
    }

    stdin_flags_ = fcntl(STDIN_FILENO, F_GETFL, 0);
    if (stdin_flags_ >= 0) {
        (void)fcntl(STDIN_FILENO, F_SETFL, stdin_flags_ | O_NONBLOCK);
    }
}

void Simulator::load_elf(const std::string &path) {
    std::vector<uint8_t> image = read_file(path);
    if (image.size() < sizeof(Elf64_Ehdr)) {
        throw std::runtime_error("ELF too small");
    }

    const auto *ehdr = reinterpret_cast<const Elf64_Ehdr *>(image.data());
    if (std::memcmp(ehdr->e_ident, ELFMAG, SELFMAG) != 0) {
        throw std::runtime_error("not an ELF file");
    }
    if (ehdr->e_ident[EI_CLASS] != ELFCLASS64) {
        throw std::runtime_error("expected ELF64 image");
    }
    if (ehdr->e_machine != EM_RISCV) {
        throw std::runtime_error("expected RISC-V ELF image");
    }

    entry_point_ = ehdr->e_entry;

    for (uint16_t i = 0; i < ehdr->e_phnum; ++i) {
        size_t offset = ehdr->e_phoff + static_cast<size_t>(i) * ehdr->e_phentsize;
        if (offset + sizeof(Elf64_Phdr) > image.size()) {
            throw std::runtime_error("truncated program header table");
        }

        const auto *phdr = reinterpret_cast<const Elf64_Phdr *>(image.data() + offset);
        if (phdr->p_type != PT_LOAD || phdr->p_memsz == 0) {
            continue;
        }
        if (phdr->p_offset + phdr->p_filesz > image.size()) {
            throw std::runtime_error("truncated PT_LOAD segment");
        }
        if (phdr->p_paddr + phdr->p_memsz < phdr->p_paddr) {
            throw std::runtime_error("segment address overflow");
        }

        write_blob(phdr->p_paddr, image.data() + phdr->p_offset, phdr->p_filesz);
        if (phdr->p_memsz > phdr->p_filesz) {
            zero_fill(phdr->p_paddr + phdr->p_filesz, phdr->p_memsz - phdr->p_filesz);
        }
    }

    load_symbols_from_elf(image, ehdr->e_shoff, ehdr->e_shentsize, ehdr->e_shnum, ehdr->e_shstrndx);
    auto tohost = symbols_.find("tohost");
    if (tohost != symbols_.end()) {
        tohost_addr_ = tohost->second;
    }
    auto fromhost = symbols_.find("fromhost");
    if (fromhost != symbols_.end()) {
        fromhost_addr_ = fromhost->second;
    }
}

void Simulator::reset() {
    exit_requested_ = false;
    exit_code_ = 0;
    running_ = true;
    stop_hart_ = 0;
    mtime_ = 0;
    fromhost_queue_.clear();
    if (tohost_addr_ != 0) {
        store64(tohost_addr_, 0);
        if (fromhost_addr_ != 0) {
            store64(fromhost_addr_, 0);
        }
    }

    for (int hart = 0; hart < options_.cores; ++hart) {
        HartState &state = harts_[hart];
        state.regs.fill(0);
        state.regs[2] = options_.ram_base + options_.ram_size - (hart * 0x10000ull) - 16;
        state.pc = entry_point_;
        state.mstatus = UINT64_C(0x0000000a00000000); // UXL=2, SXL=2 (RV64 hardwired)
        state.mie = 0;
        state.mip = 0;
        state.mtvec = 0;
        state.mcounteren = 0;
        state.menvcfg = 0;
        state.mcountinhibit = 0;
        state.medeleg = 0;
        state.mideleg = 0x1444;   /* H-ext VS interrupts hardwired-to-1 */
        state.mhpmevent.fill(0);
        state.mscratch = 0;
        state.mepc = 0;
        state.mcause = 0;
        state.mtval = 0;
        state.sepc = 0;
        state.misa = kMisaValue;
        state.mcycle = 0;
        state.minstret = 0;
        state.mhpmcounter.fill(0);
        state.reservation = UINT64_MAX;
        state.reservation_valid = false;
        state.waiting_for_interrupt = false;
        state.halted = false;
        state.single_step = false;
        state.priv_mode = 3;  // start in M-mode
        mtimecmp_[hart] = std::numeric_limits<uint64_t>::max();
    }
    // Note: mainvars are written on-demand when the program issues the
    // kSysGetmainvars (2011) syscall, so no pre-write is needed here.
    // Pre-writing at ram_base+0x1000 would corrupt ELF code loaded there
    // (e.g. arch-test rvtest_code_begin).
}

RunStats Simulator::run() {
    struct SigintHandlerGuard {
        struct sigaction old_action {};
        bool installed = false;

        ~SigintHandlerGuard() {
            if (installed) {
                (void)sigaction(SIGINT, &old_action, nullptr);
            }
        }
    } sigint_guard;

    g_sigint_requested = 0;
    struct sigaction sa {};
    sa.sa_handler = on_sigint;
    sigemptyset(&sa.sa_mask);
    sa.sa_flags = 0;
    if (sigaction(SIGINT, &sa, &sigint_guard.old_action) == 0) {
        sigint_guard.installed = true;
    }

    gdb_context_t gdb_ctx{};
    bool gdb_enabled = options_.gdb_port != 0;
    if (gdb_enabled) {
        if (gdb_stub_init(&gdb_ctx, options_.gdb_port) != 0) {
            throw std::runtime_error("failed to initialize GDB stub");
        }
        std::cerr << "GDB stub listening on tcp::" << options_.gdb_port << '\n';
        if (gdb_stub_accept(&gdb_ctx) != 0) {
            throw std::runtime_error("failed to accept GDB connection");
        }
    }

    uint64_t retired = 0;
    auto t_start = std::chrono::steady_clock::now();
    try {
        while (!exit_requested_) {
            if (g_sigint_requested != 0) {
                std::fflush(stdout);
                std::fflush(stderr);
                std::fprintf(stderr, "sim: caught Ctrl-C, dumping hart registers\n");
                dump_all_hart_registers(stderr);
                std::fflush(stderr);
                set_exit_code(130);
                break;
            }

            if (gdb_enabled && poll_gdb(&gdb_ctx) < 0) {
                break;
            }

            bool advanced = false;
            bool waiting = false;
            for (int hart = 0; hart < options_.cores; ++hart) {
                if (step_hart(hart)) {
                    advanced = true;
                    ++retired;
                    if (options_.max_instructions != 0 && retired >= options_.max_instructions) {
                        throw std::runtime_error("instruction limit reached");
                    }
                }
                if (harts_[hart].waiting_for_interrupt && !harts_[hart].halted) {
                    waiting = true;
                }
            }

            /* Advance the global CLINT mtime by one clock tick per simulator
             * loop iteration.  mtime is a platform timebase (cycle counter at
             * configCPU_CLOCK_HZ on the guest), not a sum of retired instructions
             * and not scaled by the number of active harts. */
            tick();

            service_htif();

            // Flush output streams periodically so that console output appears
            // promptly when piped or redirected (but not so often that fflush
            // syscall overhead dominates).
            if ((retired & 0xFFFFull) == 0 && retired != 0) {
                std::fflush(stdout);
                std::fflush(stderr);
            }

            if (!advanced) {
                if (waiting) {
                    continue;
                }
                break;
            }
        }
    } catch (const ExitRequest &exit_req) {
        set_exit_code(exit_req.code());
    }

    if (gdb_enabled) {
        gdb_stub_close(&gdb_ctx);
    }
    if (stdin_flags_ >= 0) {
        (void)fcntl(STDIN_FILENO, F_SETFL, stdin_flags_);
    }
    auto t_end = std::chrono::steady_clock::now();
    RunStats stats;
    stats.insns_retired = retired;
    stats.cycles        = mtime_;
    stats.wall_seconds  = std::chrono::duration<double>(t_end - t_start).count();
    return stats;
}

bool Simulator::step_hart(int hart_id) {
    HartState &hart = harts_[static_cast<size_t>(hart_id)];
    if (hart.halted || exit_requested_) {
        return false;
    }
    if (hart.waiting_for_interrupt) {
        if (!should_wake_from_wfi(hart)) {
            return false;
        }
        hart.waiting_for_interrupt = false;
    }
    step_internal(hart_id);
    if (hart.single_step) {
        hart.halted = true;
        hart.single_step = false;
        stop_hart_ = hart_id;
    }
    return true;
}

void Simulator::dump_all_hart_registers(FILE *out) const {
    static const char *kRegNames[32] = {
        "x0/zero", "x1/ra",  "x2/sp",  "x3/gp",  "x4/tp",  "x5/t0",  "x6/t1",  "x7/t2",
        "x8/s0",   "x9/s1",  "x10/a0", "x11/a1", "x12/a2", "x13/a3", "x14/a4", "x15/a5",
        "x16/a6",  "x17/a7", "x18/s2", "x19/s3", "x20/s4", "x21/s5", "x22/s6", "x23/s7",
        "x24/s8",  "x25/s9", "x26/s10", "x27/s11", "x28/t3", "x29/t4", "x30/t5", "x31/t6",
    };

    for (int hart = 0; hart < options_.cores; ++hart) {
        const HartState &state = harts_[static_cast<size_t>(hart)];
        std::fprintf(out, "hart %d:\n", hart);
        std::fprintf(out,
                     "  pc     = 0x%016llx mstatus= 0x%016llx mie     = 0x%016llx mip    = 0x%016llx\n",
                     static_cast<unsigned long long>(state.pc),
                     static_cast<unsigned long long>(state.mstatus),
                     static_cast<unsigned long long>(state.mie),
                     static_cast<unsigned long long>(state.mip));
        std::fprintf(out,
                     "  mtvec  = 0x%016llx mepc   = 0x%016llx mcause  = 0x%016llx mtval  = 0x%016llx\n",
                     static_cast<unsigned long long>(state.mtvec),
                     static_cast<unsigned long long>(state.mepc),
                     static_cast<unsigned long long>(state.mcause),
                     static_cast<unsigned long long>(state.mtval));
        std::fprintf(out,
                     "  mcycle = %llu minstret = %llu wfi = %d halted = %d\n",
                     static_cast<unsigned long long>(state.mcycle),
                     static_cast<unsigned long long>(state.minstret),
                     state.waiting_for_interrupt ? 1 : 0,
                     state.halted ? 1 : 0);
        for (int reg = 0; reg < 32; ++reg) {
            std::fprintf(out,
                         "  %-8s= 0x%016llx",
                         kRegNames[reg],
                         static_cast<unsigned long long>(state.regs[reg]));
            if ((reg % 2) == 1) {
                std::fprintf(out, "\n");
            } else {
                std::fprintf(out, "  ");
            }
        }
        if ((32 % 2) != 0) {
            std::fprintf(out, "\n");
        }
    }
}

uint64_t Simulator::read_reg(int hart_id, int reg_num) const {
    if (reg_num < 0 || reg_num >= 32) {
        return 0;
    }
    return harts_.at(static_cast<size_t>(hart_id)).regs[static_cast<size_t>(reg_num)];
}

void Simulator::write_reg(int hart_id, int reg_num, uint64_t value) {
    if (reg_num <= 0 || reg_num >= 32) {
        return;
    }
    harts_.at(static_cast<size_t>(hart_id)).regs[static_cast<size_t>(reg_num)] = value;
}

uint64_t Simulator::read_memory(uint64_t addr, unsigned size, bool exec) {
    switch (size) {
    case 1: return load8(addr, exec);
    case 2: return load16(addr, exec);
    case 4: return load32(addr, exec);
    case 8: return load64(addr, exec);
    default: throw std::runtime_error("unsupported memory read size");
    }
}

void Simulator::write_memory(uint64_t addr, uint64_t value, unsigned size) {
    switch (size) {
    case 1: store8(addr, static_cast<uint8_t>(value)); break;
    case 2: store16(addr, static_cast<uint16_t>(value)); break;
    case 4: store32(addr, static_cast<uint32_t>(value)); break;
    case 8: store64(addr, value); break;
    default: throw std::runtime_error("unsupported memory write size");
    }
}

uint64_t Simulator::get_pc(int hart_id) const { return harts_.at(static_cast<size_t>(hart_id)).pc; }
void Simulator::set_pc(int hart_id, uint64_t pc) { harts_.at(static_cast<size_t>(hart_id)).pc = pc; }
int Simulator::core_count() const { return options_.cores; }
int Simulator::focus_hart() const { return focus_hart_; }
void Simulator::set_focus_hart(int hart_id) { focus_hart_ = std::clamp(hart_id, 0, options_.cores - 1); }
int Simulator::stop_hart() const { return stop_hart_; }
bool Simulator::is_running() const { return running_ && !exit_requested_; }
void Simulator::resume_all() {
    for (auto &hart : harts_) {
        hart.halted = false;
        hart.single_step = false;
    }
}
void Simulator::halt_all() {
    for (auto &hart : harts_) {
        hart.halted = true;
    }
}
void Simulator::request_single_step(int hart_id) {
    HartState &hart = harts_.at(static_cast<size_t>(hart_id));
    hart.single_step = true;
    hart.halted = false;
}
int Simulator::exit_code() const { return exit_code_; }
bool Simulator::has_exited() const { return exit_requested_; }

void Simulator::dump_signature(const std::string &path, uint32_t granularity) const {
    auto begin_it = symbols_.find("begin_signature");
    auto end_it   = symbols_.find("end_signature");
    if (begin_it == symbols_.end() || end_it == symbols_.end()) {
        std::cerr << "sim: dump_signature: begin_signature/end_signature not found in ELF\n";
        return;
    }
    uint64_t begin_addr = begin_it->second;
    uint64_t end_addr   = end_it->second;
    if (end_addr <= begin_addr) {
        std::cerr << "sim: dump_signature: empty signature region\n";
        return;
    }
    if (granularity == 0 || (granularity & (granularity - 1)) != 0 ||
        granularity > 8) {
        throw std::invalid_argument("signature-granularity must be 1, 2, 4, or 8");
    }

    std::ofstream out(path);
    if (!out) {
        throw std::runtime_error("dump_signature: cannot open '" + path + "' for writing");
    }
    out << std::hex << std::setfill('0');

    for (uint64_t addr = begin_addr; addr < end_addr; addr += granularity) {
        uint64_t word = 0;
        for (uint32_t b = 0; b < granularity; ++b) {
            uint64_t off = (addr + b) - options_.ram_base;
            uint8_t byte = (off < options_.ram_size) ? flat_ram_[static_cast<size_t>(off)] : 0;
            word |= static_cast<uint64_t>(byte) << (b * 8);
        }
        out << std::setw(granularity * 2) << word << '\n';
    }
}

int Simulator::poll_gdb(gdb_context_t *ctx) {
    gdb_callbacks_t callbacks{};
    callbacks.read_reg = [](void *opaque, int reg_num) -> uint64_t {
        auto *sim = static_cast<Simulator *>(opaque);
        return sim->read_reg(sim->focus_hart(), reg_num);
    };
    callbacks.write_reg = [](void *opaque, int reg_num, uint64_t value) {
        auto *sim = static_cast<Simulator *>(opaque);
        sim->write_reg(sim->focus_hart(), reg_num, value);
    };
    callbacks.read_mem = [](void *opaque, uint64_t addr, int size) -> uint64_t {
        auto *sim = static_cast<Simulator *>(opaque);
        return sim->read_memory(addr, static_cast<unsigned>(size));
    };
    callbacks.write_mem = [](void *opaque, uint64_t addr, uint64_t value, int size) {
        auto *sim = static_cast<Simulator *>(opaque);
        sim->write_memory(addr, value, static_cast<unsigned>(size));
    };
    callbacks.get_pc = [](void *opaque) -> uint64_t {
        auto *sim = static_cast<Simulator *>(opaque);
        return sim->get_pc(sim->focus_hart());
    };
    callbacks.set_pc = [](void *opaque, uint64_t pc) {
        auto *sim = static_cast<Simulator *>(opaque);
        sim->set_pc(sim->focus_hart(), pc);
    };
    callbacks.single_step = [](void *opaque) {
        auto *sim = static_cast<Simulator *>(opaque);
        sim->request_single_step(sim->focus_hart());
    };
    callbacks.is_running = [](void *opaque) -> bool {
        auto *sim = static_cast<Simulator *>(opaque);
        return sim->is_running();
    };
    callbacks.reset = [](void *opaque) { static_cast<Simulator *>(opaque)->reset(); };
    callbacks.resume = [](void *opaque) { static_cast<Simulator *>(opaque)->resume_all(); };
    callbacks.get_num_harts = [](void *opaque) -> int { return static_cast<Simulator *>(opaque)->core_count(); };
    callbacks.set_focus_hart = [](void *opaque, int hart) { static_cast<Simulator *>(opaque)->set_focus_hart(hart); };
    callbacks.get_focus_hart = [](void *opaque) -> int { return static_cast<Simulator *>(opaque)->focus_hart(); };
    callbacks.get_stop_hart = [](void *opaque) -> int { return static_cast<Simulator *>(opaque)->stop_hart() + 1; };
    callbacks.halt_cpus = [](void *opaque) { static_cast<Simulator *>(opaque)->halt_all(); };
    return gdb_stub_process(ctx, this, &callbacks);
}

void Simulator::ensure_page(uint64_t addr) {
    pages_.try_emplace(addr / kPageSize);
}

Simulator::Page *Simulator::find_page(uint64_t addr) {
    auto it = pages_.find(addr / kPageSize);
    return it == pages_.end() ? nullptr : &it->second;
}

const Simulator::Page *Simulator::find_page(uint64_t addr) const {
    auto it = pages_.find(addr / kPageSize);
    return it == pages_.end() ? nullptr : &it->second;
}

uint8_t Simulator::load8(uint64_t addr, bool exec) {
    // Fast path: flat RAM
    uint64_t off = addr - options_.ram_base;
    if (__builtin_expect(off < options_.ram_size, 1)) {
        return flat_ram_[static_cast<size_t>(off)];
    }
    uint64_t mmio = 0;
    if (read_mmio(addr, 1, mmio)) {
        return static_cast<uint8_t>(mmio);
    }
    const Page *page = find_page(addr);
    if (!page) {
        if (exec) {
            throw Trap(kInsnAccessFault, addr, "instruction access fault");
        }
        // Only raise a load access fault for the arch-test fault-injection
        // address range (RVMODEL_ACCESS_FAULT_ADDRESS = 0x00000000).  All
        // other unmapped reads silently return 0, preserving the original
        // behaviour that FreeRTOS (and crt0.S) relies on.
        if (addr < 0x1000) {
            throw Trap(kLoadAccessFault, addr, "load access fault");
        }
        return 0;
    }
    return page->bytes[static_cast<size_t>(addr % kPageSize)];
}

uint16_t Simulator::load16(uint64_t addr, bool exec) {
    uint16_t value = 0;
    for (unsigned i = 0; i < 2; ++i) {
        value |= static_cast<uint16_t>(load8(addr + i, exec)) << (i * 8);
    }
    return value;
}

uint32_t Simulator::load32(uint64_t addr, bool exec) {
    // Fast path: aligned flat-RAM access
    uint64_t off = addr - options_.ram_base;
    if (__builtin_expect((addr & 3u) == 0 && off + 4 <= options_.ram_size, 1)) {
        uint32_t v;
        __builtin_memcpy(&v, &flat_ram_[static_cast<size_t>(off)], sizeof(v));
        return v;
    }
    uint32_t value = 0;
    for (unsigned i = 0; i < 4; ++i) {
        value |= static_cast<uint32_t>(load8(addr + i, exec)) << (i * 8);
    }
    return value;
}

uint64_t Simulator::load64(uint64_t addr, bool exec) {
    // Fast path: aligned flat-RAM access
    uint64_t off = addr - options_.ram_base;
    if (__builtin_expect((addr & 7u) == 0 && off + 8 <= options_.ram_size, 1)) {
        uint64_t v;
        __builtin_memcpy(&v, &flat_ram_[static_cast<size_t>(off)], sizeof(v));
        return v;
    }
    uint64_t value = 0;
    for (unsigned i = 0; i < 8; ++i) {
        value |= static_cast<uint64_t>(load8(addr + i, exec)) << (i * 8);
    }
    return value;
}

void Simulator::store8(uint64_t addr, uint8_t value) {
    // Fast path: flat RAM
    uint64_t off = addr - options_.ram_base;
    if (__builtin_expect(off < options_.ram_size, 1)) {
        flat_ram_[static_cast<size_t>(off)] = value;
        return;
    }
    if (write_mmio(addr, value, 1)) {
        return;
    }
    // Only raise a store access fault for the arch-test fault-injection address
    // range (RVMODEL_ACCESS_FAULT_ADDRESS = 0x00000000).  For all other unmapped
    // addresses auto-allocate a sparse page (original behaviour) so that normal
    // firmware writes (e.g. crt0.S releasing secondary harts via out-of-range
    // CLINT MSIP slots) do not cause spurious traps.
    auto it = pages_.find(addr / kPageSize);
    if (it == pages_.end()) {
        if (addr < 0x1000) {
            throw Trap(kStoreAccessFault, addr, "store access fault");
        }
        pages_[addr / kPageSize] = Page{};
        pages_[addr / kPageSize].bytes[static_cast<size_t>(addr % kPageSize)] = value;
        return;
    }
    it->second.bytes[static_cast<size_t>(addr % kPageSize)] = value;
}

void Simulator::store16(uint64_t addr, uint16_t value) {
    for (unsigned i = 0; i < 2; ++i) {
        store8(addr + i, static_cast<uint8_t>(value >> (i * 8)));
    }
}

void Simulator::store32(uint64_t addr, uint32_t value) {
    // Fast path: aligned flat-RAM access
    uint64_t off = addr - options_.ram_base;
    if (__builtin_expect((addr & 3u) == 0 && off + 4 <= options_.ram_size, 1)) {
        __builtin_memcpy(&flat_ram_[static_cast<size_t>(off)], &value, sizeof(value));
        return;
    }
    for (unsigned i = 0; i < 4; ++i) {
        store8(addr + i, static_cast<uint8_t>(value >> (i * 8)));
    }
}

void Simulator::store64(uint64_t addr, uint64_t value) {
    // Fast path: aligned flat-RAM access
    uint64_t off = addr - options_.ram_base;
    if (__builtin_expect((addr & 7u) == 0 && off + 8 <= options_.ram_size, 1)) {
        __builtin_memcpy(&flat_ram_[static_cast<size_t>(off)], &value, sizeof(value));
        if (__builtin_expect(tohost_addr_ != 0 && addr == tohost_addr_ && value != 0, false)) {
            htif_tohost_dirty_ = true;
        }
        return;
    }
    for (unsigned i = 0; i < 8; ++i) {
        store8(addr + i, static_cast<uint8_t>(value >> (i * 8)));
    }
    if (__builtin_expect(tohost_addr_ != 0 && addr == tohost_addr_ && value != 0, false)) {
        htif_tohost_dirty_ = true;
    }
}

bool Simulator::read_mmio(uint64_t addr, unsigned size, uint64_t &value) {
    if (addr >= kClintBase && addr + size <= kClintBase + 4ull * options_.cores) {
        size_t hart = static_cast<size_t>((addr - kClintBase) / 4);
        size_t offs = static_cast<size_t>((addr - kClintBase) % 4);
        uint64_t msip = (harts_[hart].mip & kMipMsip) ? 1ull : 0ull;
        value = (msip >> (offs * 8)) & mask_for_size(size);
        return true;
    }
    if (addr >= kMtimeBase && addr + size <= kMtimeBase + 8) {
        value = (mtime_ >> ((addr - kMtimeBase) * 8)) & mask_for_size(size);
        return true;
    }
    if (addr >= kMtimecmpBase && addr + size <= kMtimecmpBase + 8ull * options_.cores) {
        size_t hart = static_cast<size_t>((addr - kMtimecmpBase) / 8);
        size_t offs = static_cast<size_t>((addr - kMtimecmpBase) % 8);
        value = (mtimecmp_[hart] >> (offs * 8)) & mask_for_size(size);
        return true;
    }
    return false;
}

bool Simulator::write_mmio(uint64_t addr, uint64_t value, unsigned size) {
    if (addr >= kClintBase && addr + size <= kClintBase + 4ull * options_.cores) {
        size_t hart = static_cast<size_t>((addr - kClintBase) / 4);
        size_t offs = static_cast<size_t>((addr - kClintBase) % 4);
        uint64_t shift = offs * 8;
        uint64_t mask = mask_for_size(size) << shift;
        uint64_t msip = ((harts_[hart].mip & kMipMsip) ? 1ull : 0ull);
        msip = (msip & ~mask) | ((value & mask_for_size(size)) << shift);
        if ((msip & 1u) != 0) {
            harts_[hart].mip |= kMipMsip;
        } else {
            harts_[hart].mip &= ~kMipMsip;
        }
        return true;
    }
    if (addr >= kMtimeBase && addr + size <= kMtimeBase + 8) {
        uint64_t shift = (addr - kMtimeBase) * 8;
        uint64_t mask = mask_for_size(size) << shift;
        mtime_ = (mtime_ & ~mask) | ((value & mask_for_size(size)) << shift);
        return true;
    }
    if (addr >= kMtimecmpBase && addr + size <= kMtimecmpBase + 8ull * options_.cores) {
        size_t hart = static_cast<size_t>((addr - kMtimecmpBase) / 8);
        size_t offs = static_cast<size_t>((addr - kMtimecmpBase) % 8);
        uint64_t mask = mask_for_size(size) << (offs * 8);
        mtimecmp_[hart] = (mtimecmp_[hart] & ~mask) | ((value & mask_for_size(size)) << (offs * 8));
        return true;
    }
    return false;
}

void Simulator::write_blob(uint64_t addr, const void *data, size_t len) {
    // Fast path: fully within flat RAM (covers virtually all ELF load and
    // syscall-write paths).
    uint64_t off = addr - options_.ram_base;
    if (__builtin_expect(off + len <= options_.ram_size, 1)) {
        std::memcpy(&flat_ram_[static_cast<size_t>(off)], data, len);
        return;
    }
    const auto *bytes = static_cast<const uint8_t *>(data);
    for (size_t i = 0; i < len; ++i) {
        store8(addr + i, bytes[i]);
    }
}

void Simulator::zero_fill(uint64_t addr, size_t len) {
    // Fast path: fully within flat RAM.
    uint64_t off = addr - options_.ram_base;
    if (__builtin_expect(off + len <= options_.ram_size, 1)) {
        std::memset(&flat_ram_[static_cast<size_t>(off)], 0, len);
        return;
    }
    for (size_t i = 0; i < len; ++i) {
        store8(addr + i, 0);
    }
}

void Simulator::load_symbols_from_elf(const std::vector<uint8_t> &image, uint64_t shoff,
                                      uint16_t shentsize, uint16_t shnum, uint16_t) {
    if (shoff == 0 || shnum == 0) {
        return;
    }
    for (uint16_t i = 0; i < shnum; ++i) {
        size_t offset = static_cast<size_t>(shoff) + static_cast<size_t>(i) * shentsize;
        if (offset + sizeof(Elf64_Shdr) > image.size()) {
            throw std::runtime_error("truncated section header table");
        }
        const auto *shdr = reinterpret_cast<const Elf64_Shdr *>(image.data() + offset);
        if (shdr->sh_type != SHT_SYMTAB) {
            continue;
        }
        if (shdr->sh_offset + shdr->sh_size > image.size()) {
            throw std::runtime_error("truncated symbol table");
        }
        if (shdr->sh_link >= shnum) {
            throw std::runtime_error("invalid symbol string table index");
        }

        const auto *strhdr = reinterpret_cast<const Elf64_Shdr *>(image.data() + shoff + static_cast<size_t>(shdr->sh_link) * shentsize);
        if (strhdr->sh_offset + strhdr->sh_size > image.size()) {
            throw std::runtime_error("truncated string table");
        }
        const char *strtab = reinterpret_cast<const char *>(image.data() + strhdr->sh_offset);
        size_t count = shdr->sh_size / sizeof(Elf64_Sym);
        for (size_t symi = 0; symi < count; ++symi) {
            const auto *sym = reinterpret_cast<const Elf64_Sym *>(image.data() + shdr->sh_offset + symi * sizeof(Elf64_Sym));
            if (sym->st_name >= strhdr->sh_size) {
                continue;
            }
            std::string name(strtab + sym->st_name);
            if (!name.empty()) {
                symbols_[name] = sym->st_value;
            }
        }
    }
}

void Simulator::service_htif() {
    if (tohost_addr_ == 0) {
        return;
    }
    if (htif_tohost_dirty_) {
        htif_tohost_dirty_ = false;
        uint64_t tohost = load64(tohost_addr_);
        if (tohost != 0) {
            store64(tohost_addr_, 0);
            handle_htif_command(tohost);
        }
    }
    // fromhost delivery only makes sense when the ELF defines a fromhost symbol
    if (fromhost_addr_ != 0) {
        try_deliver_fromhost();
    }
}

void Simulator::queue_fromhost(uint64_t value) { fromhost_queue_.push_back(value); }

void Simulator::try_deliver_fromhost() {
    if (fromhost_queue_.empty() || fromhost_addr_ == 0) {
        return;
    }
    if (load64(fromhost_addr_) != 0) {
        return;
    }
    store64(fromhost_addr_, fromhost_queue_.front());
    fromhost_queue_.pop_front();
}

void Simulator::handle_htif_command(uint64_t value) {
    uint8_t dev = static_cast<uint8_t>(value >> 56);
    uint8_t cmd = static_cast<uint8_t>(value >> 48);
    uint64_t payload = value & 0x0000FFFFFFFFFFFFull;

    if (dev == kHtifDevConsole) {
        handle_htif_console(cmd, payload);
        return;
    }
    if (dev == kHtifDevSyscall && cmd == 0) {
        if (payload & 1u) {
            set_exit_code(static_cast<int>(payload >> 1));
        } else {
            handle_htif_syscall(payload);
        }
        return;
    }
    complete_htif_request(dev, cmd, 1);
}

void Simulator::handle_htif_console(uint8_t cmd, uint64_t payload) {
    if (cmd == 1) {
        char ch = static_cast<char>(payload & 0xFFu);
        (void)!write(STDOUT_FILENO, &ch, 1);
        complete_htif_request(kHtifDevConsole, cmd, payload & 0xFFu);
        return;
    }
    if (cmd == 0) {
        char ch = 0;
        ssize_t rc = read(STDIN_FILENO, &ch, 1);
        uint64_t response = rc == 1 ? static_cast<uint8_t>(ch) : 0;
        complete_htif_request(kHtifDevConsole, cmd, response);
        return;
    }
    complete_htif_request(kHtifDevConsole, cmd, 0);
}

void Simulator::handle_htif_syscall(uint64_t payload) {
    std::array<uint64_t, 8> magic{};
    for (size_t i = 0; i < magic.size(); ++i) {
        magic[i] = load64(payload + i * sizeof(uint64_t));
    }

    auto sysret = [](long rc) -> uint64_t {
        return rc == -1 ? static_cast<uint64_t>(-errno) : static_cast<uint64_t>(rc);
    };

    uint64_t syscall_no = magic[0];
    uint64_t result = static_cast<uint64_t>(-ENOSYS);
    switch (syscall_no) {
    case kSysExit:
        throw ExitRequest(static_cast<int>(magic[1]));
    case kSysOpenat: {
        std::string path = read_c_string(magic[2], magic[3]);
        result = sysret(host_openat(static_cast<int>(magic[1]), path, static_cast<int>(magic[4]), static_cast<int>(magic[5])));
        break;
    }
    case kSysClose:
        // Never close the simulator's own stdin/stdout/stderr even if the
        // guest closes fds 0-2 during newlib exit() cleanup.
        if (static_cast<int>(magic[1]) >= 3) {
            result = sysret(close(static_cast<int>(magic[1])));
        } else {
            result = 0;
        }
        break;
    case kSysRead: {
        std::vector<char> buf(static_cast<size_t>(magic[3]));
        ssize_t rc = read(static_cast<int>(magic[1]), buf.data(), buf.size());
        if (rc > 0) {
            write_blob(magic[2], buf.data(), static_cast<size_t>(rc));
        }
        result = sysret(rc);
        break;
    }
    case kSysWrite: {
        std::vector<char> buf(static_cast<size_t>(magic[3]));
        for (size_t i = 0; i < buf.size(); ++i) {
            buf[i] = static_cast<char>(load8(magic[2] + i));
        }
        result = sysret(write(static_cast<int>(magic[1]), buf.data(), buf.size()));
        break;
    }
    case kSysPread: {
        std::vector<char> buf(static_cast<size_t>(magic[3]));
        ssize_t rc = pread(static_cast<int>(magic[1]), buf.data(), buf.size(), static_cast<off_t>(magic[4]));
        if (rc > 0) {
            write_blob(magic[2], buf.data(), static_cast<size_t>(rc));
        }
        result = sysret(rc);
        break;
    }
    case kSysPwrite: {
        std::vector<char> buf(static_cast<size_t>(magic[3]));
        for (size_t i = 0; i < buf.size(); ++i) {
            buf[i] = static_cast<char>(load8(magic[2] + i));
        }
        result = sysret(pwrite(static_cast<int>(magic[1]), buf.data(), buf.size(), static_cast<off_t>(magic[4])));
        break;
    }
    case kSysLseek:
        result = sysret(lseek(static_cast<int>(magic[1]), static_cast<off_t>(magic[2]), static_cast<int>(magic[3])));
        break;
    case kSysFstat:
    case kSysFstatat: {
        struct ::stat st {};
        int rc = -1;
        if (syscall_no == kSysFstat) {
            rc = fstat(static_cast<int>(magic[1]), &st);
            if (rc == 0) {
                write_stat(magic[2], st);
            }
        } else {
            std::string path = read_c_string(magic[2], magic[3]);
            rc = fstatat(host_dirfd(static_cast<int>(magic[1])), path.c_str(), &st, static_cast<int>(magic[5]));
            if (rc == 0) {
                write_stat(magic[4], st);
            }
        }
        result = sysret(rc);
        break;
    }
    case kSysFaccessat: {
        std::string path = read_c_string(magic[2], magic[3]);
        result = sysret(faccessat(host_dirfd(static_cast<int>(magic[1])), path.c_str(), static_cast<int>(magic[4]), 0));
        break;
    }
    case kSysMkdirat: {
        std::string path = read_c_string(magic[2], magic[3]);
        result = sysret(mkdirat(host_dirfd(static_cast<int>(magic[1])), path.c_str(), static_cast<mode_t>(magic[4])));
        break;
    }
    case kSysUnlinkat: {
        std::string path = read_c_string(magic[2], magic[3]);
        result = sysret(unlinkat(host_dirfd(static_cast<int>(magic[1])), path.c_str(), static_cast<int>(magic[4])));
        break;
    }
    case kSysRenameat: {
        std::string old_path = read_c_string(magic[2], magic[3]);
        std::string new_path = read_c_string(magic[5], magic[6]);
        result = sysret(renameat(host_dirfd(static_cast<int>(magic[1])), old_path.c_str(),
                                 host_dirfd(static_cast<int>(magic[4])), new_path.c_str()));
        break;
    }
    case kSysLinkat: {
        std::string old_path = read_c_string(magic[2], magic[3]);
        std::string new_path = read_c_string(magic[5], magic[6]);
        result = sysret(linkat(host_dirfd(static_cast<int>(magic[1])), old_path.c_str(),
                               host_dirfd(static_cast<int>(magic[4])), new_path.c_str(), static_cast<int>(magic[7])));
        break;
    }
    case kSysGetcwd: {
        std::vector<char> buf(static_cast<size_t>(magic[2]));
        char *cwd = getcwd(buf.data(), buf.size());
        if (cwd != nullptr) {
            write_blob(magic[1], cwd, std::strlen(cwd) + 1);
            result = std::strlen(cwd) + 1;
        } else {
            result = static_cast<uint64_t>(-errno);
        }
        break;
    }
    case kSysChdir: {
        std::string path = read_c_string(magic[1]);
        result = sysret(chdir(path.c_str()));
        break;
    }
    case kSysReadlinkat: {
        std::string path = read_c_string(magic[2], magic[3]);
        std::vector<char> buf(static_cast<size_t>(magic[5]));
        ssize_t rc = readlinkat(host_dirfd(static_cast<int>(magic[1])), path.c_str(), buf.data(), buf.size());
        if (rc > 0) {
            write_blob(magic[4], buf.data(), static_cast<size_t>(rc));
        }
        result = sysret(rc);
        break;
    }
    case kSysFcntl:
        result = sysret(fcntl(static_cast<int>(magic[1]), static_cast<int>(magic[2]), static_cast<int>(magic[3])));
        break;
    case kSysGetmainvars:
        write_mainvars(magic[1], magic[2]);
        result = 0;
        break;
    case kSysReadv:
    case kSysWritev:
        result = static_cast<uint64_t>(-ENOSYS);
        break;
    default:
        result = static_cast<uint64_t>(-ENOSYS);
        break;
    }

    magic[0] = result;
    for (size_t i = 0; i < magic.size(); ++i) {
        store64(payload + i * sizeof(uint64_t), magic[i]);
    }
    complete_htif_request(kHtifDevSyscall, 0, 1);
}

void Simulator::complete_htif_request(uint8_t dev, uint8_t cmd, uint64_t payload) {
    queue_fromhost((static_cast<uint64_t>(dev) << 56) |
                   (static_cast<uint64_t>(cmd) << 48) |
                   (payload & 0x0000FFFFFFFFFFFFull));
}

void Simulator::set_exit_code(int code) {
    exit_requested_ = true;
    exit_code_ = code;
    running_ = false;
}

// Translate Newlib (bare-metal RISC-V) open flags to Linux host open flags.
// Newlib's _default_fcntl.h uses different bit positions than Linux.
static int translate_newlib_open_flags(int newlib_flags) {
    // Access mode (bits 0-1) are identical in both.
    int host_flags = newlib_flags & O_ACCMODE;

    // Newlib → Linux flag mapping (only the bits that differ).
    struct { int nb; int host; } map[] = {
        { 0x0008, O_APPEND    },  // _FAPPEND
        { 0x0200, O_CREAT     },  // _FCREAT
        { 0x0400, O_TRUNC     },  // _FTRUNC
        { 0x0800, O_EXCL      },  // _FEXCL
        { 0x2000, O_SYNC      },  // _FSYNC  (best effort)
        { 0x4000, O_NONBLOCK  },  // _FNONBLOCK
        { 0x8000, O_NOCTTY    },  // _FNOCTTY
#ifdef O_CLOEXEC
        { 0x040000, O_CLOEXEC   },  // _FNOINHERIT
#endif
#ifdef O_NOFOLLOW
        { 0x100000, O_NOFOLLOW  },  // _FNOFOLLOW
#endif
#ifdef O_DIRECTORY
        { 0x200000, O_DIRECTORY },  // _FDIRECTORY
#endif
    };
    for (const auto &e : map) {
        if (newlib_flags & e.nb) {
            host_flags |= e.host;
        }
    }
    return host_flags;
}

int Simulator::host_openat(int dirfd, const std::string &path, int flags, int mode) const {
    return openat(host_dirfd(dirfd), path.c_str(), translate_newlib_open_flags(flags), mode);
}

int Simulator::host_dirfd(int dirfd) const {
    return dirfd == kAtFdcwd ? AT_FDCWD : dirfd;
}

std::string Simulator::read_c_string(uint64_t addr, uint64_t len_hint) {
    std::string out;
    if (len_hint != 0) {
        out.reserve(static_cast<size_t>(len_hint));
        for (uint64_t i = 0; i < len_hint; ++i) {
            char c = static_cast<char>(load8(addr + i));
            if (c == '\0') {
                break;
            }
            out.push_back(c);
        }
        return out;
    }
    for (;;) {
        char c = static_cast<char>(load8(addr++));
        if (c == '\0') {
            break;
        }
        out.push_back(c);
    }
    return out;
}

void Simulator::write_stat(uint64_t addr, const HostStat &host_stat) {
    RiscvStat st{};
    st.dev = static_cast<uint64_t>(host_stat.st_dev);
    st.ino = static_cast<uint64_t>(host_stat.st_ino);
    st.mode = static_cast<uint32_t>(host_stat.st_mode);
    st.nlink = static_cast<uint32_t>(host_stat.st_nlink);
    st.uid = static_cast<uint32_t>(host_stat.st_uid);
    st.gid = static_cast<uint32_t>(host_stat.st_gid);
    st.rdev = static_cast<uint64_t>(host_stat.st_rdev);
    st.size = static_cast<uint64_t>(host_stat.st_size);
    st.blksize = static_cast<uint32_t>(host_stat.st_blksize);
    st.blocks = static_cast<uint64_t>(host_stat.st_blocks);
    st.atime = static_cast<uint64_t>(host_stat.st_atime);
    st.mtime = static_cast<uint64_t>(host_stat.st_mtime);
    st.ctime = static_cast<uint64_t>(host_stat.st_ctime);
    write_blob(addr, &st, sizeof(st));
}

void Simulator::write_mainvars(uint64_t addr, uint64_t limit) {
    std::vector<std::string> args;
    args.push_back(options_.elf_path);
    args.insert(args.end(), options_.target_args.begin(), options_.target_args.end());

    std::vector<uint64_t> words(args.size() + 3, 0);
    words[0] = static_cast<uint64_t>(args.size());
    size_t offset = words.size() * sizeof(uint64_t);
    std::vector<uint8_t> blob(offset);
    std::memcpy(blob.data(), words.data(), offset);

    for (size_t i = 0; i < args.size(); ++i) {
        uint64_t ptr = addr + offset;
        std::memcpy(blob.data() + (i + 1) * sizeof(uint64_t), &ptr, sizeof(ptr));
        blob.insert(blob.end(), args[i].begin(), args[i].end());
        blob.push_back('\0');
        offset = blob.size();
    }

    if (blob.size() > limit) {
        return;
    }
    write_blob(addr, blob.data(), blob.size());
}

void Simulator::tick() {
    ++mtime_;
    for (int hart = 0; hart < options_.cores; ++hart) {
        if (mtime_ >= mtimecmp_[hart]) {
            harts_[hart].mip |= kMipMtip;
        } else {
            harts_[hart].mip &= ~kMipMtip;
        }
    }
}

void Simulator::step_internal(int hart_id) {
    HartState &hart = harts_[hart_id];
    if (handle_interrupt(hart_id)) {
        return;
    }

    bool compressed = false;
    uint64_t trap_pc = hart.pc;
    uint32_t insn = 0;
    bool insn_fetched = false;
    try {
        insn = fetch_insn32(hart_id, compressed);
        insn_fetched = true;
        int      trace_priv = 0;
        uint32_t trace_raw  = 0;
        if (options_.trace && g_sigint_requested == 0) {
            commit_log_.clear();
            trace_priv = static_cast<int>(hart.priv_mode);
            trace_raw  = compressed ? static_cast<uint32_t>(load16(trap_pc)) : insn;
        }
        execute32(hart_id, insn, compressed);
        hart.regs[0] = 0;
        if ((hart.mcountinhibit & (1ull << 2)) == 0) ++hart.minstret;
        if (options_.trace && g_sigint_requested == 0) {
            static RiscvDisassembler dis;
            std::string disasm = dis.disassemble(trace_raw, trap_pc);
            char hdr[80];
            std::snprintf(hdr, sizeof(hdr), "core %3d: %d 0x%016" PRIx64 " (0x%08x)",
                          hart_id, trace_priv, trap_pc, trace_raw);
            // Build each commit line into a prefix buffer, then align the
            // disassembly comment to column 90.
            char prefix[200];
            if (commit_log_.empty()) {
                std::snprintf(prefix, sizeof(prefix), "%s", hdr);
                std::fprintf(stderr, "%-90s; %s\n", prefix, disasm.c_str());
            } else {
                bool first = true;
                for (const auto &e : commit_log_) {
                    switch (e.kind) {
                    case CommitEntry::Kind::Reg:
                        std::snprintf(prefix, sizeof(prefix), "%s %-4s 0x%016" PRIx64,
                                      hdr, kRegAbiNames[e.num], e.val);
                        break;
                    case CommitEntry::Kind::MemR:
                    case CommitEntry::Kind::MemW:
                        std::snprintf(prefix, sizeof(prefix),
                                      "%s mem 0x%016" PRIx64 " 0x%016" PRIx64,
                                      hdr, e.addr, e.val);
                        break;
                    case CommitEntry::Kind::Csr: {
                        char cname[20];
                        const char *cn = csr_name_for_log(e.num);
                        if (!cn) { std::snprintf(cname, sizeof(cname), "0x%03x", e.num); cn = cname; }
                        std::snprintf(prefix, sizeof(prefix), "%s csr %-16s 0x%016" PRIx64,
                                      hdr, cn, e.val);
                        break;
                    }
                    }
                    if (first) {
                        std::fprintf(stderr, "%-90s; %s\n", prefix, disasm.c_str());
                        first = false;
                    } else {
                        std::fprintf(stderr, "%s\n", prefix);
                    }
                }
            }
        }
    } catch (const Trap &trap) {
        // For illegal instruction exceptions the spec requires mtval to hold the
        // faulting instruction word.  Helpers like csr_read/csr_write currently
        // store only a partial value (e.g. the CSR number) as the tval, so
        // override it with the full instruction word whenever we successfully
        // fetched the instruction before the trap was raised.
        if (insn_fetched && trap.cause() == kIllegalInstruction) {
            execute_trap(hart_id, Trap(kIllegalInstruction, insn, trap.what()), trap_pc, true);
        } else {
            execute_trap(hart_id, trap, trap_pc, true);
        }
    }
    if ((hart.mcountinhibit & (1ull << 0)) == 0) ++hart.mcycle;
}

void Simulator::execute_trap(int hart_id, const Trap &trap, uint64_t trap_pc, bool) {
    HartState &hart = harts_[hart_id];
    hart.waiting_for_interrupt = false;
    // Standard M-mode trap entry: MPIE←MIE, MIE←0, MPP←priv_mode, then switch to M
    uint64_t mie = (hart.mstatus >> 3) & 1;
    hart.mstatus = (hart.mstatus & ~(1ull << 7)) | (mie << 7); // MPIE ← MIE
    hart.mstatus &= ~(1ull << 3);                               // MIE ← 0
    hart.mstatus = (hart.mstatus & ~(3ull << 11)) | (static_cast<uint64_t>(hart.priv_mode) << 11); // MPP ← priv
    hart.priv_mode = 3;  // now executing in M-mode
    hart.mepc = trap_pc;
    hart.mcause = trap.cause();
    hart.mtval = trap.tval();
    hart.pc = hart.mtvec;
    if (trap.cause() == kBreakpoint && options_.gdb_port != 0) {
        hart.halted = true;
        stop_hart_ = hart_id;
    }
}

bool Simulator::handle_interrupt(int hart_id) {
    HartState &hart = harts_[hart_id];
    if ((hart.mstatus & kMstatusMie) == 0) {
        return false;
    }
    auto do_int_trap = [&](uint64_t cause) {
        uint64_t mie_bit = (hart.mstatus >> 3) & 1;
        hart.mstatus = (hart.mstatus & ~(1ull << 7)) | (mie_bit << 7); // MPIE ← MIE
        hart.mstatus &= ~(1ull << 3);                               // MIE ← 0
        hart.mstatus = (hart.mstatus & ~(3ull << 11)) | (static_cast<uint64_t>(hart.priv_mode) << 11); // MPP ← priv
        hart.priv_mode = 3;  // now in M-mode
        hart.mepc = hart.pc;
        hart.mcause = cause;
        hart.mtval = 0;
        hart.pc = hart.mtvec;
    };
    if ((hart.mie & kMieMsip) && (hart.mip & kMipMsip)) {
        do_int_trap(kMachineSoftwareInterrupt);
        return true;
    }
    if ((hart.mie & kMieMtip) && (hart.mip & kMipMtip)) {
        do_int_trap(kMachineTimerInterrupt);
        return true;
    }
    return false;
}

bool Simulator::should_wake_from_wfi(const HartState &hart) const {
    return (hart.mie & hart.mip & (kMieMsip | kMieMtip)) != 0;
}

uint32_t Simulator::fetch_insn32(int hart_id, bool &compressed) {
    HartState &hart = harts_[hart_id];
    uint16_t half = load16(hart.pc, true);
    if ((half & 0x3) != 0x3) {
        compressed = true;
        return decompress(half);
    }
    compressed = false;
    return load32(hart.pc, true);
}

uint32_t Simulator::decompress(uint16_t insn) const {
    uint32_t op = insn & 0x3;
    uint32_t funct3 = (insn >> 13) & 0x7;

    switch (op) {
    case 0:
        switch (funct3) {
        case 0: {
            uint32_t rd = 8 + ((insn >> 2) & 0x7);
            uint32_t imm = ((insn >> 7) & 0x30) | ((insn >> 1) & 0x3C0) | ((insn >> 4) & 0x4) | ((insn >> 2) & 0x8);
            return (imm << 20) | (2 << 15) | (0 << 12) | (rd << 7) | 0x13;
        }
        case 2: {
            uint32_t rd = 8 + ((insn >> 2) & 0x7);
            uint32_t rs1 = 8 + ((insn >> 7) & 0x7);
            uint32_t imm = ((insn >> 10) & 0x7) << 3 | ((insn >> 5) & 0x1) << 6 | ((insn >> 6) & 0x1) << 2;
            return (imm << 20) | (rs1 << 15) | (2 << 12) | (rd << 7) | 0x03;
        }
        case 3: {
            uint32_t rd = 8 + ((insn >> 2) & 0x7);
            uint32_t rs1 = 8 + ((insn >> 7) & 0x7);
            uint32_t imm = ((insn >> 10) & 0x7) << 3 | ((insn >> 5) & 0x3) << 6;
            return (imm << 20) | (rs1 << 15) | (3 << 12) | (rd << 7) | 0x03;
        }
        case 6: {
            uint32_t rs2 = 8 + ((insn >> 2) & 0x7);
            uint32_t rs1 = 8 + ((insn >> 7) & 0x7);
            uint32_t imm = ((insn >> 10) & 0x7) << 3 | ((insn >> 5) & 0x1) << 6 | ((insn >> 6) & 0x1) << 2;
            return ((imm >> 5) << 25) | (rs2 << 20) | (rs1 << 15) | (2 << 12) | ((imm & 0x1F) << 7) | 0x23;
        }
        case 7: {
            uint32_t rs2 = 8 + ((insn >> 2) & 0x7);
            uint32_t rs1 = 8 + ((insn >> 7) & 0x7);
            uint32_t imm = ((insn >> 10) & 0x7) << 3 | ((insn >> 5) & 0x3) << 6;
            return ((imm >> 5) << 25) | (rs2 << 20) | (rs1 << 15) | (3 << 12) | ((imm & 0x1F) << 7) | 0x23;
        }
        default:
            break;
        }
        break;
    case 1:
        switch (funct3) {
        case 0: {
            uint32_t rd = (insn >> 7) & 0x1F;
            uint32_t imm = ((insn >> 2) & 0x1F) | ((insn >> 12) & 0x1) << 5;
            imm = static_cast<uint32_t>(sign_extend(imm, 6));
            return ((imm & 0xFFF) << 20) | (rd << 15) | (0 << 12) | (rd << 7) | 0x13;
        }
        case 1: {
            /* C.ADDIW (RV64); in RV32 this encoding is C.JAL — not supported here */
            uint32_t rd = (insn >> 7) & 0x1F;
            uint32_t imm = ((insn >> 2) & 0x1F) | ((insn >> 12) & 0x1) << 5;
            imm = static_cast<uint32_t>(sign_extend(imm, 6));
            return ((imm & 0xFFF) << 20) | (rd << 15) | (0 << 12) | (rd << 7) | 0x1B;
        }
        case 2: {
            uint32_t rd = (insn >> 7) & 0x1F;
            uint32_t imm = ((insn >> 2) & 0x1F) | ((insn >> 12) & 0x1) << 5;
            imm = static_cast<uint32_t>(sign_extend(imm, 6));
            return ((imm & 0xFFF) << 20) | (0 << 15) | (0 << 12) | (rd << 7) | 0x13;
        }
        case 3: {
            uint32_t rd = (insn >> 7) & 0x1F;
            uint32_t imm;
            if (rd == 2) {
                imm = ((insn >> 3) & 0x3) << 7 | ((insn >> 5) & 0x1) << 6 | ((insn >> 2) & 0x1) << 5 |
                      ((insn >> 6) & 0x1) << 4 | ((insn >> 12) & 0x1) << 9;
                imm = static_cast<uint32_t>(sign_extend(imm, 10));
                return ((imm & 0xFFF) << 20) | (2 << 15) | (0 << 12) | (2 << 7) | 0x13;
            }
            imm = ((insn >> 2) & 0x1F) | ((insn >> 12) & 0x1) << 5;
            imm = static_cast<uint32_t>(sign_extend(imm, 6)) << 12;
            return (imm & 0xFFFFF000u) | (rd << 7) | 0x37;
        }
        case 4: {
            uint32_t rd = 8 + ((insn >> 7) & 0x7);
            uint32_t funct2 = (insn >> 10) & 0x3;
            if (funct2 == 0) {
                uint32_t shamt = ((insn >> 2) & 0x1F) | ((insn >> 12) & 0x1) << 5;
                return (shamt << 20) | (rd << 15) | (5 << 12) | (rd << 7) | 0x13;
            }
            if (funct2 == 1) {
                uint32_t shamt = ((insn >> 2) & 0x1F) | ((insn >> 12) & 0x1) << 5;
                return (0x20u << 25) | (shamt << 20) | (rd << 15) | (5 << 12) | (rd << 7) | 0x13;
            }
            if (funct2 == 2) {
                uint32_t imm = ((insn >> 2) & 0x1F) | ((insn >> 12) & 0x1) << 5;
                imm = static_cast<uint32_t>(sign_extend(imm, 6));
                return ((imm & 0xFFF) << 20) | (rd << 15) | (7 << 12) | (rd << 7) | 0x13;
            }
            uint32_t rs2 = 8 + ((insn >> 2) & 0x7);
            uint32_t subop = ((insn >> 5) & 0x3) | ((insn >> 12) & 0x1) << 2;
            switch (subop) {
            case 0: return (0x20u << 25) | (rs2 << 20) | (rd << 15) | (0 << 12) | (rd << 7) | 0x33;
            case 1: return (0x00u << 25) | (rs2 << 20) | (rd << 15) | (4 << 12) | (rd << 7) | 0x33;
            case 2: return (0x00u << 25) | (rs2 << 20) | (rd << 15) | (6 << 12) | (rd << 7) | 0x33;
            case 3: return (0x00u << 25) | (rs2 << 20) | (rd << 15) | (7 << 12) | (rd << 7) | 0x33;
            case 4: return (0x20u << 25) | (rs2 << 20) | (rd << 15) | (0 << 12) | (rd << 7) | 0x3B;
            case 5: return (0x00u << 25) | (rs2 << 20) | (rd << 15) | (0 << 12) | (rd << 7) | 0x3B;
            default: break;
            }
            break;
        }
        case 5:
            return encode_jal(0, encode_rvc_j_imm(insn));
        case 6: {
            uint32_t rs1 = 8 + ((insn >> 7) & 0x7);
            uint32_t imm = static_cast<uint32_t>(encode_rvc_b_imm(insn));
            return (((imm >> 12) & 0x1) << 31) | (((imm >> 5) & 0x3F) << 25) | (0 << 20) |
                   (rs1 << 15) | (0 << 12) | (((imm >> 1) & 0xF) << 8) | (((imm >> 11) & 0x1) << 7) | 0x63;
        }
        case 7: {
            uint32_t rs1 = 8 + ((insn >> 7) & 0x7);
            uint32_t imm = static_cast<uint32_t>(encode_rvc_b_imm(insn));
            return (((imm >> 12) & 0x1) << 31) | (((imm >> 5) & 0x3F) << 25) | (0 << 20) |
                   (rs1 << 15) | (1 << 12) | (((imm >> 1) & 0xF) << 8) | (((imm >> 11) & 0x1) << 7) | 0x63;
        }
        default:
            break;
        }
        break;
    case 2:
        switch (funct3) {
        case 0: {
            uint32_t rd = (insn >> 7) & 0x1F;
            uint32_t shamt = ((insn >> 2) & 0x1F) | ((insn >> 12) & 0x1) << 5;
            return (shamt << 20) | (rd << 15) | (1 << 12) | (rd << 7) | 0x13;
        }
        case 2: {
            uint32_t rd = (insn >> 7) & 0x1F;
            uint32_t imm = ((insn >> 4) & 0x7) << 2 | ((insn >> 12) & 0x1) << 5 | ((insn >> 2) & 0x3) << 6;
            return (imm << 20) | (2 << 15) | (2 << 12) | (rd << 7) | 0x03;
        }
        case 3: {
            /* C.LDSP: offset[8:6]=inst[4:2], offset[5]=inst[12], offset[4:3]=inst[6:5] */
            uint32_t rd = (insn >> 7) & 0x1F;
            uint32_t imm = ((insn >> 2) & 0x7) << 6 | ((insn >> 12) & 0x1) << 5 | ((insn >> 5) & 0x3) << 3;
            return (imm << 20) | (2 << 15) | (3 << 12) | (rd << 7) | 0x03;
        }
        case 4: {
            uint32_t rs2 = (insn >> 2) & 0x1F;
            uint32_t rd = (insn >> 7) & 0x1F;
            if (((insn >> 12) & 0x1) == 0) {
                if (rs2 == 0) {
                    return (0 << 20) | (rd << 15) | (0 << 12) | (0 << 7) | 0x67;
                }
                return (0 << 25) | (rs2 << 20) | (0 << 15) | (0 << 12) | (rd << 7) | 0x33;
            }
            if (rs2 == 0 && rd == 0) {
                return 0x00100073;
            }
            if (rs2 == 0) {
                return (0 << 20) | (rd << 15) | (0 << 12) | (1 << 7) | 0x67;
            }
            return (0 << 25) | (rs2 << 20) | (rd << 15) | (0 << 12) | (rd << 7) | 0x33;
        }
        case 6: {
            uint32_t rs2 = (insn >> 2) & 0x1F;
            uint32_t imm = ((insn >> 9) & 0xF) << 2 | ((insn >> 7) & 0x3) << 6;
            return ((imm >> 5) << 25) | (rs2 << 20) | (2 << 15) | (2 << 12) | ((imm & 0x1F) << 7) | 0x23;
        }
        case 7: {
            uint32_t rs2 = (insn >> 2) & 0x1F;
            uint32_t imm = ((insn >> 10) & 0x7) << 3 | ((insn >> 7) & 0x7) << 6;
            return ((imm >> 5) << 25) | (rs2 << 20) | (2 << 15) | (3 << 12) | ((imm & 0x1F) << 7) | 0x23;
        }
        default:
            break;
        }
        break;
    default:
        break;
    }
    throw Trap(kIllegalInstruction, insn, "unsupported compressed instruction");
}

void Simulator::execute32(int hart_id, uint32_t insn, bool compressed) {
    HartState &hart = harts_[hart_id];
    uint32_t opcode = insn & 0x7F;
    uint32_t rd = bits(insn, 11, 7);
    uint32_t funct3 = bits(insn, 14, 12);
    uint32_t rs1 = bits(insn, 19, 15);
    uint32_t rs2 = bits(insn, 24, 20);
    uint32_t funct7 = bits(insn, 31, 25);
    uint64_t next_pc = hart.pc + (compressed ? 2 : 4);
    auto &regs = hart.regs;
    auto write_rd = [&](uint64_t value) {
        if (rd != 0) {
            regs[rd] = value;
            if (options_.trace) {
                commit_log_.push_back({CommitEntry::Kind::Reg, rd, 0, value, 0});
            }
        }
    };
    auto log_mem_r = [&](uint64_t maddr, uint64_t mval) {
        if (options_.trace) commit_log_.push_back({CommitEntry::Kind::MemR, 0, maddr, mval, 0});
    };
    auto log_mem_w = [&](uint64_t maddr, uint64_t mval) {
        if (options_.trace) commit_log_.push_back({CommitEntry::Kind::MemW, 0, maddr, mval, 0});
    };
    auto log_csr = [&](uint32_t csr_num, uint64_t oval, uint64_t nval) {
        if (options_.trace) commit_log_.push_back({CommitEntry::Kind::Csr, csr_num, 0, nval, oval});
    };

    switch (opcode) {
    case 0x03: {
        uint64_t addr = regs[rs1] + encode_i_imm(insn);
        switch (funct3) {
        case 0: { uint64_t v = sign_extend(load8(addr),  8);  write_rd(v); log_mem_r(addr, v); break; }
        case 1:
            if (addr & 1) throw Trap(kLoadAddrMisaligned, addr, "misaligned lh");
            { uint64_t v = sign_extend(load16(addr), 16); write_rd(v); log_mem_r(addr, v); break; }
        case 2:
            if (addr & 3) throw Trap(kLoadAddrMisaligned, addr, "misaligned lw");
            { uint64_t v = sign_extend(load32(addr), 32); write_rd(v); log_mem_r(addr, v); break; }
        case 3:
            if (addr & 7) throw Trap(kLoadAddrMisaligned, addr, "misaligned ld");
            { uint64_t v = load64(addr);                  write_rd(v); log_mem_r(addr, v); break; }
        case 4: { uint64_t v = load8(addr);  write_rd(v); log_mem_r(addr, v); break; }
        case 5:
            if (addr & 1) throw Trap(kLoadAddrMisaligned, addr, "misaligned lhu");
            { uint64_t v = load16(addr);                  write_rd(v); log_mem_r(addr, v); break; }
        case 6:
            if (addr & 3) throw Trap(kLoadAddrMisaligned, addr, "misaligned lwu");
            { uint64_t v = load32(addr);                  write_rd(v); log_mem_r(addr, v); break; }
        default: throw Trap(kIllegalInstruction, insn, "illegal load");
        }
        break;
    }
    case 0x0F:
        break;
    case 0x13: {
        uint64_t imm = encode_i_imm(insn);
        switch (funct3) {
        case 0: write_rd(regs[rs1] + imm); break;
        case 1: write_rd(regs[rs1] << (imm & 0x3F)); break;
        case 2: write_rd(static_cast<int64_t>(regs[rs1]) < static_cast<int64_t>(imm) ? 1 : 0); break;
        case 3: write_rd(regs[rs1] < imm ? 1 : 0); break;
        case 4: write_rd(regs[rs1] ^ imm); break;
        case 5:
            if ((imm & 0x400) == 0) {
                write_rd(regs[rs1] >> (imm & 0x3F));
            } else {
                write_rd(static_cast<uint64_t>(arithmetic_shift_right(static_cast<int64_t>(regs[rs1]), imm & 0x3F)));
            }
            break;
        case 6: write_rd(regs[rs1] | imm); break;
        case 7: write_rd(regs[rs1] & imm); break;
        default: throw Trap(kIllegalInstruction, insn, "illegal op-imm");
        }
        break;
    }
    case 0x17:
        write_rd(hart.pc + encode_u_imm(insn));
        break;
    case 0x1B: {
        uint64_t imm = encode_i_imm(insn);
        switch (funct3) {
        case 0: write_rd(sign_extend(static_cast<uint32_t>(regs[rs1] + imm), 32)); break;
        case 1: write_rd(sign_extend(static_cast<uint32_t>(regs[rs1]) << (rs2 & 0x1F), 32)); break;
        case 5:
            if (funct7 == 0x00) {
                write_rd(sign_extend(static_cast<uint32_t>(regs[rs1]) >> (rs2 & 0x1F), 32));
            } else if (funct7 == 0x20) {
                write_rd(sign_extend(static_cast<uint32_t>(arithmetic_shift_right(static_cast<int32_t>(regs[rs1]), rs2 & 0x1F)), 32));
            } else {
                throw Trap(kIllegalInstruction, insn, "illegal op-imm-32");
            }
            break;
        default: throw Trap(kIllegalInstruction, insn, "illegal op-imm-32");
        }
        break;
    }
    case 0x23: {
        uint64_t addr = regs[rs1] + encode_s_imm(insn);
        switch (funct3) {
        case 0: store8( addr, static_cast<uint8_t>( regs[rs2])); log_mem_w(addr, regs[rs2] & 0xFFu);         break;
        case 1:
            if (addr & 1) throw Trap(kStoreAddrMisaligned, addr, "misaligned sh");
            store16(addr, static_cast<uint16_t>(regs[rs2]));
            log_mem_w(addr, regs[rs2] & 0xFFFFu);
            break;
        case 2:
            if (addr & 3) throw Trap(kStoreAddrMisaligned, addr, "misaligned sw");
            store32(addr, static_cast<uint32_t>(regs[rs2]));
            log_mem_w(addr, regs[rs2] & 0xFFFFFFFFu);
            break;
        case 3:
            if (addr & 7) throw Trap(kStoreAddrMisaligned, addr, "misaligned sd");
            store64(addr, regs[rs2]);
            log_mem_w(addr, regs[rs2]);
            break;
        default: throw Trap(kIllegalInstruction, insn, "illegal store");
        }
        break;
    }
    case 0x2F: {
        bool word = funct3 == 2;
        bool dword = funct3 == 3;
        if (!word && !dword) {
            throw Trap(kIllegalInstruction, insn, "illegal atomic width");
        }
        uint64_t addr = regs[rs1];
        uint32_t funct5 = bits(insn, 31, 27);
        // Misaligned LR/SC/AMO: LRSC_MISALIGNED_BEHAVIOR = "always raise access fault".
        // LR is a load, so misaligned LR raises Load access fault (cause=5).
        // SC and all AMOs raise Store/AMO access fault (cause=7).
        if (word  && (addr & 3u)) throw Trap(funct5 == 0x02 ? kLoadAccessFault : kStoreAccessFault, addr, "misaligned atomic .w");
        if (dword && (addr & 7u)) throw Trap(funct5 == 0x02 ? kLoadAccessFault : kStoreAccessFault, addr, "misaligned atomic .d");

        if (funct5 == 0x02) {
            // LR: load-reserved
            // Set reservation BEFORE the load attempt so that SC can fault
            // correctly even if LR itself faults — matching Spike's behaviour.
            hart.reservation = addr;
            hart.reservation_valid = true;
            uint64_t loaded = dword ? load64(addr) : sign_extend(load32(addr), 32);
            write_rd(loaded);
            log_mem_r(addr, loaded);
        } else if (funct5 == 0x03) {
            // SC: store-conditional
            if (hart.reservation_valid && hart.reservation == addr) {
                if (dword) {
                    store64(addr, regs[rs2]);
                } else {
                    store32(addr, static_cast<uint32_t>(regs[rs2]));
                }
                log_mem_w(addr, regs[rs2]);
                write_rd(0);
            } else {
                write_rd(1);
            }
            hart.reservation_valid = false;
        } else {
            // AMO: atomic read-modify-write.
            // Access faults from the load phase must be reported as
            // Store/AMO access fault (cause=7) — matching Spike behaviour.
            uint64_t loaded;
            try {
                loaded = dword ? load64(addr) : sign_extend(load32(addr), 32);
            } catch (const Trap &t) {
                throw Trap(kStoreAccessFault, t.tval(), t.what());
            }
            uint64_t result = amo_op(funct5, loaded, regs[rs2], word);
            if (dword) {
                store64(addr, result);
                log_mem_r(addr, loaded);
                log_mem_w(addr, result);
                write_rd(loaded);
            } else {
                uint64_t wv = sign_extend(static_cast<uint32_t>(loaded), 32);
                store32(addr, static_cast<uint32_t>(result));
                log_mem_r(addr, wv);
                log_mem_w(addr, result & 0xFFFFFFFFu);
                write_rd(wv);
            }
        }
        break;
    }
    case 0x33: {
        switch ((funct7 << 3) | funct3) {
        case (0x00 << 3) | 0: write_rd(regs[rs1] + regs[rs2]); break;
        case (0x20 << 3) | 0: write_rd(regs[rs1] - regs[rs2]); break;
        case (0x00 << 3) | 1: write_rd(regs[rs1] << (regs[rs2] & 0x3F)); break;
        case (0x00 << 3) | 2: write_rd(static_cast<int64_t>(regs[rs1]) < static_cast<int64_t>(regs[rs2]) ? 1 : 0); break;
        case (0x00 << 3) | 3: write_rd(regs[rs1] < regs[rs2] ? 1 : 0); break;
        case (0x00 << 3) | 4: write_rd(regs[rs1] ^ regs[rs2]); break;
        case (0x00 << 3) | 5: write_rd(regs[rs1] >> (regs[rs2] & 0x3F)); break;
        case (0x20 << 3) | 5: write_rd(static_cast<uint64_t>(arithmetic_shift_right(static_cast<int64_t>(regs[rs1]), regs[rs2] & 0x3F))); break;
        case (0x00 << 3) | 6: write_rd(regs[rs1] | regs[rs2]); break;
        case (0x00 << 3) | 7: write_rd(regs[rs1] & regs[rs2]); break;
        case (0x01 << 3) | 0: write_rd(regs[rs1] * regs[rs2]); break;
        case (0x01 << 3) | 1: write_rd(static_cast<uint64_t>((__int128_t)(static_cast<int64_t>(regs[rs1])) * (__int128_t)(static_cast<int64_t>(regs[rs2])) >> 64)); break;
        case (0x01 << 3) | 2: write_rd(static_cast<uint64_t>((__int128_t)(static_cast<int64_t>(regs[rs1])) * (__int128_t)(regs[rs2]) >> 64)); break;
        case (0x01 << 3) | 3: write_rd(mulhu_u64(regs[rs1], regs[rs2])); break;
        case (0x01 << 3) | 4:
            if (regs[rs2] == 0) write_rd(UINT64_MAX);
            else if (regs[rs1] == (1ull << 63) && regs[rs2] == UINT64_MAX) write_rd(regs[rs1]);
            else write_rd(static_cast<uint64_t>(static_cast<int64_t>(regs[rs1]) / static_cast<int64_t>(regs[rs2])));
            break;
        case (0x01 << 3) | 5:
            write_rd(regs[rs2] == 0 ? UINT64_MAX : regs[rs1] / regs[rs2]);
            break;
        case (0x01 << 3) | 6:
            if (regs[rs2] == 0) write_rd(regs[rs1]);
            else if (regs[rs1] == (1ull << 63) && regs[rs2] == UINT64_MAX) write_rd(0);
            else write_rd(static_cast<uint64_t>(static_cast<int64_t>(regs[rs1]) % static_cast<int64_t>(regs[rs2])));
            break;
        case (0x01 << 3) | 7:
            write_rd(regs[rs2] == 0 ? regs[rs1] : regs[rs1] % regs[rs2]);
            break;
        default: throw Trap(kIllegalInstruction, insn, "illegal op");
        }
        break;
    }
    case 0x37:
        write_rd(encode_u_imm(insn));
        break;
    case 0x3B: {
        uint32_t lhs = static_cast<uint32_t>(regs[rs1]);
        uint32_t rhs = static_cast<uint32_t>(regs[rs2]);
        switch ((funct7 << 3) | funct3) {
        case (0x00 << 3) | 0: write_rd(sign_extend(lhs + rhs, 32)); break;
        case (0x20 << 3) | 0: write_rd(sign_extend(lhs - rhs, 32)); break;
        case (0x00 << 3) | 1: write_rd(sign_extend(lhs << (rhs & 0x1F), 32)); break;
        case (0x00 << 3) | 5: write_rd(sign_extend(lhs >> (rhs & 0x1F), 32)); break;
        case (0x20 << 3) | 5: write_rd(sign_extend(static_cast<uint32_t>(static_cast<int32_t>(lhs) >> (rhs & 0x1F)), 32)); break;
        case (0x01 << 3) | 0: write_rd(sign_extend(lhs * rhs, 32)); break;
        case (0x01 << 3) | 4:
            write_rd(sign_extend(rhs == 0 ? 0xFFFFFFFFu : static_cast<uint32_t>(static_cast<int32_t>(lhs) / static_cast<int32_t>(rhs)), 32));
            break;
        case (0x01 << 3) | 5: write_rd(sign_extend(rhs == 0 ? 0xFFFFFFFFu : lhs / rhs, 32)); break;
        case (0x01 << 3) | 6: write_rd(sign_extend(rhs == 0 ? lhs : static_cast<uint32_t>(static_cast<int32_t>(lhs) % static_cast<int32_t>(rhs)), 32)); break;
        case (0x01 << 3) | 7: write_rd(sign_extend(rhs == 0 ? lhs : lhs % rhs, 32)); break;
        default: throw Trap(kIllegalInstruction, insn, "illegal op-32");
        }
        break;
    }
    case 0x63: {
        uint64_t target = hart.pc + encode_b_imm(insn);
        bool take = false;
        switch (funct3) {
        case 0: take = regs[rs1] == regs[rs2]; break;
        case 1: take = regs[rs1] != regs[rs2]; break;
        case 4: take = static_cast<int64_t>(regs[rs1]) < static_cast<int64_t>(regs[rs2]); break;
        case 5: take = static_cast<int64_t>(regs[rs1]) >= static_cast<int64_t>(regs[rs2]); break;
        case 6: take = regs[rs1] < regs[rs2]; break;
        case 7: take = regs[rs1] >= regs[rs2]; break;
        default: throw Trap(kIllegalInstruction, insn, "illegal branch");
        }
        if (take) next_pc = target;
        break;
    }
    case 0x67: {
        uint64_t target = (regs[rs1] + encode_i_imm(insn)) & ~1ull;
        write_rd(next_pc);
        next_pc = target;
        break;
    }
    case 0x6F:
        write_rd(next_pc);
        next_pc = hart.pc + encode_j_imm(insn);
        break;
    case 0x73: {
        uint32_t csr = bits(insn, 31, 20);
        if (funct3 == 0) {
            uint32_t imm12 = bits(insn, 31, 20);
            if (imm12 == 0) {
                throw Trap(kEcallFromMmode, 0, "ecall");
            }
            if (imm12 == 1) {
                throw Trap(kBreakpoint, hart.pc, "ebreak");
            }
            if (imm12 == 0x105) {
                hart.waiting_for_interrupt = true;
                break;
            }
            if (imm12 == 0x302) {  /* mret */
                uint64_t mpie = (hart.mstatus >> 7) & 1;
                uint64_t mpp  = (hart.mstatus >> 11) & 3;
                hart.priv_mode = static_cast<uint32_t>(mpp); // priv ← MPP
                /* MIE ← MPIE */
                hart.mstatus = (hart.mstatus & ~(1ull << 3)) | (mpie << 3);
                /* MPIE ← 1 */
                hart.mstatus |= (1ull << 7);
                /* MPP ← U (0) */
                hart.mstatus &= ~(3ull << 11);
                /* MPRV ← 0 if new priv mode != M (spec: §3.1.6.1) */
                if (mpp != 3) hart.mstatus &= ~(1ull << 17);
                next_pc = hart.mepc;
                break;
            }
            if (imm12 == 0x102) {  /* sret */
                /* From M-mode sret is always legal (TSR only restricts S-mode sret) */
                uint64_t spie = (hart.mstatus >> 5) & 1;
                hart.priv_mode = static_cast<uint32_t>((hart.mstatus >> 8) & 1); // priv ← SPP
                hart.mstatus = (hart.mstatus & ~(1ull << 1)) | (spie << 1); /* SIE ← SPIE */
                hart.mstatus |= (1ull << 5);  /* SPIE ← 1 */
                hart.mstatus &= ~(1ull << 8); /* SPP ← U (0) */
                /* MPRV always cleared on sret (spec: §3.1.6.1) */
                hart.mstatus &= ~(1ull << 17);
                next_pc = hart.sepc;
                break;
            }
            throw Trap(kIllegalInstruction, insn, "illegal system");
        }
        uint64_t old = csr_read(hart, csr);
        uint64_t src = (funct3 & 0x4) ? rs1 : regs[rs1];
        uint64_t new_csr = old;
        bool csr_written = false;
        switch (funct3 & 0x3) {
        case 1: new_csr = src; csr_write(hart, csr, new_csr); csr_written = true; break;
        case 2:
            if (src != 0) {
                new_csr = old | src;
                csr_write(hart, csr, new_csr);
                csr_written = true;
            }
            break;
        case 3:
            if (src != 0) {
                new_csr = old & ~src;
                csr_write(hart, csr, new_csr);
                csr_written = true;
            }
            break;
        default: throw Trap(kIllegalInstruction, insn, "illegal csr");
        }
        if (csr_written) log_csr(csr, old, new_csr);
        write_rd(old);
        break;
    }
    default:
        throw Trap(kIllegalInstruction, insn, "unsupported opcode");
    }

    hart.pc = next_pc;
}

uint64_t Simulator::csr_read(HartState &hart, uint32_t csr) const {
    /* ── M-mode read/write CSRs (0x3xx) ──────────────────────────────── */
    switch (csr) {
    case 0x300: {
        uint64_t ms = hart.mstatus;
        uint64_t vs = (ms >>  9) & 3;
        uint64_t fs = (ms >> 13) & 3;
        // XS always 0: no user-mode extensions in this simulator
        ms &= ~(3ull << 15);
        // SD = 1 if FS or VS is Dirty (3)
        if (fs == 3 || vs == 3) ms |=  (UINT64_C(1) << 63);
        else                    ms &= ~(UINT64_C(1) << 63);
        return ms;
    }
    case 0x301: return hart.misa;
    case 0x302: return hart.medeleg;
    case 0x303: return hart.mideleg;
    case 0x304: return hart.mie;
    case 0x305: return hart.mtvec;
    case 0x306: return hart.mcounteren;
    case 0x30A: return hart.menvcfg;
    case 0x320: return hart.mcountinhibit;
    case 0x340: return hart.mscratch;
    case 0x341: return hart.mepc;
    case 0x342: return hart.mcause;
    case 0x343: return hart.mtval;
    case 0x344: return hart.mip;
    /* ── S-mode sepc (0x141) ── */
    case 0x141: return hart.sepc;
    /* ── mhpmevent3..31 (0x323..0x33F) ── */
    default:
        if (csr >= 0x323 && csr <= 0x33F)
            return hart.mhpmevent[csr - 0x323];
        /* ── M-mode performance counters (0xBxx) ── */
        if (csr == 0xB00) return hart.mcycle;
        if (csr == 0xB02) return hart.minstret;
        if (csr >= 0xB03 && csr <= 0xB1F) return 0; /* mhpmcounterN — no HPM hw, read-only zero */
        /* ── User-mode counter aliases (0xCxx) — read-only ── */
        if (csr == 0xC00) return hart.mcycle;    /* cycle  */
        if (csr == 0xC01) return mtime_;         /* time   */
        if (csr == 0xC02) return hart.minstret;  /* instret */
        if (csr >= 0xC03 && csr <= 0xC1F) return 0; /* hpmcounterN — no HPM hw */
        /* ── Read-only machine info CSRs (0xFxx) ── */
        if (csr == 0xF11) return 0;            /* mvendorid */
        if (csr == 0xF12) return 5;            /* marchid: 5 = Berkeley Rocket (matches Spike default) */
        if (csr == 0xF13) return 0;            /* mimpid: 0 = not implemented (matches Spike default) */
        if (csr == 0xF14) return static_cast<uint64_t>(&hart - harts_.data()); /* mhartid */
        if (csr == 0xF15) return 0;            /* mconfigptr */
        throw Trap(kIllegalInstruction, csr, "unsupported csr read");
    }
}

void Simulator::csr_write(HartState &hart, uint32_t csr, uint64_t value) {
    /* Architecturally read-only: CSR address bits[11:10] == 11 (0xC00-0xFFF) */
    if ((csr >> 10) == 3)
        throw Trap(kIllegalInstruction, csr, "write to read-only csr");
    /* medeleg (0x302) and mideleg (0x303): WARL — store only legal bits.
     * mideleg bits 2,6,10,12 (VS-mode / SGEI interrupts) are hardwired to 1. */
    if (csr == 0x302) { hart.medeleg = value & UINT64_C(0x00fcb7fe); return; }
    if (csr == 0x303) { hart.mideleg = (value & UINT64_C(0x2222)) | UINT64_C(0x1444); return; }

    switch (csr) {
    case 0x300: {
        uint64_t new_ms = (hart.mstatus & ~kMstatusWriteMask) | (value & kMstatusWriteMask);
        // WARL: MPP (bits 12:11). The encoding 0b10 (value 2) is reserved and
        // not a valid RISC-V privilege mode. Match Spike's behaviour: clear to
        // 0b00 when the reserved value is written, but allow 0b00/0b01/0b11.
        if (((new_ms >> 11) & 3) == 2) {
            new_ms &= ~(3ull << 11);  // clear MPP to 0b00
        }
        hart.mstatus = new_ms;
        break;
    }
    case 0x304: hart.mie = value & UINT64_C(0x3eee); break;
    case 0x305: hart.mtvec = value & ~UINT64_C(2); break;  /* MODE: only 0=direct,1=vectored legal; bit 1 always 0 */
    case 0x306: hart.mcounteren = value & UINT64_C(0xffffffff); break;  /* RV64: upper 32 bits hardwired 0 */
    case 0x30A: {  /* menvcfg: write mask covers Sstc/Svpbmt/Svadu/Zicbom/Zicboz bits */
        uint64_t new_menvcfg = value & UINT64_C(0xe0000000000000fc);
        /* WARL: CBIE field [5:4] — value 0b10 is reserved; match Spike behaviour: clear to 0b00 */
        if (((new_menvcfg >> 4) & 0x3) == 0x2) new_menvcfg &= ~UINT64_C(0x30);
        hart.menvcfg = new_menvcfg;
        break;
    }
    case 0x320: hart.mcountinhibit = value & UINT64_C(0xfffffffd); break;  /* 32-bit; bit 1 hardwired 0 */
    case 0x340: hart.mscratch = value; break;
    case 0x341: hart.mepc = value & ~UINT64_C(1); break;  /* bit 0 hardwired 0 (IALIGN=16) */
    case 0x342: hart.mcause = value; break;
    case 0x343: hart.mtval = value; break;
    case 0x344: {  /* mip: only SW-writable bits (SSIP/VSSIP/STIP/SEIP/bit13); MSIP/MTIP are hardware-driven */
        constexpr uint64_t kMipSwMask = UINT64_C(0x2226);
        hart.mip = (hart.mip & ~kMipSwMask) | (value & kMipSwMask);
        break;
    }
    /* ── S-mode sepc (0x141) ── */
    case 0x141: hart.sepc = value & ~UINT64_C(1); break;  /* bit 0 hardwired 0 */
    case 0x301: {  /* misa: WARL — A(0), C(2), M(12) writable; I(8) and MXL(63:62) fixed */
        constexpr uint64_t kMisaWriteMask = (1ull << 0) | (1ull << 2) | (1ull << 12);
        uint64_t new_misa = (kMisaValue & ~kMisaWriteMask) | (value & kMisaWriteMask);
        /* WARL: misa.C (bit 2) may only be cleared when the csrX instruction is 4-byte
         * aligned. If PC is 2-byte aligned, the next PC (PC+4) would also be 2-byte
         * aligned, which would cause an immediate misalignment fault — match Spike's
         * behaviour by preserving the current misa.C in that case. */
        if (!(value & (1ull << 2)) && (hart.pc & 3) != 0) {
            new_misa |= (hart.misa & (1ull << 2));   /* restore old C bit */
        }
        hart.misa = new_misa;
        break;
    }
    case 0xB00: hart.mcycle = value; break;
    case 0xB02: hart.minstret = value; break;
    default:
        if (csr >= 0x323 && csr <= 0x33F) { hart.mhpmevent[csr - 0x323] = value & UINT64_C(0xfc00000000000000); break; }  /* WARL: only inhibit/OF bits */
        if (csr >= 0xB03 && csr <= 0xB1F) { break; }  /* mhpmcounterN — no HPM hw; silently ignore writes */
        throw Trap(kIllegalInstruction, csr, "unsupported csr write");
    }
}

uint64_t Simulator::amo_op(uint32_t funct5, uint64_t lhs, uint64_t rhs, bool word) const {
    auto norm = [&](uint64_t value) {
        return word ? sign_extend(static_cast<uint32_t>(value), 32) : value;
    };
    lhs = norm(lhs);
    rhs = norm(rhs);
    switch (funct5) {
    case 0x01: return rhs;
    case 0x00: return lhs + rhs;
    case 0x04: return lhs ^ rhs;
    case 0x0C: return lhs & rhs;
    case 0x08: return lhs | rhs;
    case 0x10: return static_cast<int64_t>(lhs) < static_cast<int64_t>(rhs) ? lhs : rhs;
    case 0x14: return static_cast<int64_t>(lhs) > static_cast<int64_t>(rhs) ? lhs : rhs;
    case 0x18: return lhs < rhs ? lhs : rhs;
    case 0x1C: return lhs > rhs ? lhs : rhs;
    default: throw Trap(kIllegalInstruction, funct5, "unsupported amo op");
    }
}

uint64_t Simulator::sign_extend(uint64_t value, unsigned bits) {
    uint64_t shift = 64 - bits;
    return static_cast<uint64_t>(static_cast<int64_t>(value << shift) >> shift);
}

uint64_t Simulator::mask_for_size(unsigned size) {
    return size >= 8 ? UINT64_MAX : ((1ull << (size * 8)) - 1ull);
}

int64_t Simulator::arithmetic_shift_right(int64_t value, unsigned shamt) {
    return value >> shamt;
}

uint64_t Simulator::load_u(const std::vector<uint8_t> &buf, size_t offset, size_t size) {
    uint64_t value = 0;
    for (size_t i = 0; i < size; ++i) {
        value |= static_cast<uint64_t>(buf.at(offset + i)) << (i * 8);
    }
    return value;
}

} // namespace sim
