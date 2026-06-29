// ============================================================================
// File: sim/main.cpp
// Project: FreeRTOS-RISCV-SMP
// Description: Entry point for the riscv64-sim software simulator.
//
// Parses command-line options and drives the Simulator class to load and
// execute a RISC-V ELF binary.  Supports --trace (instruction-level trace
// with disassembly), --test-signature (RISC-V arch-test signature dump),
// --max-insns, and GDB remote stub.
//
// Usage:
//   riscv64-sim [options] <elf>
//   riscv64-sim --trace --max-insns <N> <elf>
//   riscv64-sim --test-signature=<file> --signature-granularity 4 <elf>
// ============================================================================

#include <cerrno>
#include <cstdlib>
#include <cstring>
#include <cstdio>
#include <cinttypes>
#include <iostream>
#include <stdexcept>
#include <unistd.h>

#include "simulator.h"

namespace {

using sim::Options;
using sim::Simulator;

void usage(const char *argv0) {
    std::cerr
        << "Usage: " << argv0 << " [options] program.elf [target args...]\n"
        << "  --cores N                    Number of harts to simulate (1-16)\n"
        << "  --memory MB                  RAM size in MiB (default 128)\n"
        << "  --ram-base HEX               RAM base physical address (default 0x80000000)\n"
        << "  --gdb PORT                   Start GDB remote stub on TCP PORT\n"
        << "  --max-insns N                Stop after retiring N instructions\n"
        << "  --trace                      Print each executed instruction PC\n"
        << "  --no-stats                   Suppress simulation statistics on exit\n"
        << "  --test-signature=<file>      Dump arch-test signature to <file> after exit\n"
        << "  --signature-granularity <N>  Signature word size in bytes (default 4)\n";
}

uint64_t parse_u64(const char *text) {
    char *end = nullptr;
    errno = 0;
    unsigned long long value = std::strtoull(text, &end, 0);
    if (errno != 0 || end == text || *end != '\0') {
        throw std::invalid_argument(std::string("invalid integer: ") + text);
    }
    return static_cast<uint64_t>(value);
}

Options parse_args(int argc, char **argv) {
    Options options;

    for (int i = 1; i < argc; ++i) {
        const char *arg = argv[i];
        if (std::strcmp(arg, "--cores") == 0) {
            if (++i >= argc) {
                throw std::invalid_argument("--cores requires an argument");
            }
            options.cores = static_cast<int>(parse_u64(argv[i]));
        } else if (std::strcmp(arg, "--memory") == 0) {
            if (++i >= argc) {
                throw std::invalid_argument("--memory requires an argument");
            }
            options.ram_size = parse_u64(argv[i]) * 1024ull * 1024ull;
        } else if (std::strcmp(arg, "--ram-base") == 0) {
            if (++i >= argc) {
                throw std::invalid_argument("--ram-base requires an argument");
            }
            options.ram_base = parse_u64(argv[i]);
        } else if (std::strcmp(arg, "--gdb") == 0) {
            if (++i >= argc) {
                throw std::invalid_argument("--gdb requires an argument");
            }
            options.gdb_port = static_cast<uint16_t>(parse_u64(argv[i]));
        } else if (std::strcmp(arg, "--max-insns") == 0) {
            if (++i >= argc) {
                throw std::invalid_argument("--max-insns requires an argument");
            }
            options.max_instructions = parse_u64(argv[i]);
        } else if (std::strcmp(arg, "--trace") == 0) {
            options.trace = true;
        } else if (std::strncmp(arg, "--test-signature=", 17) == 0) {
            options.test_signature = arg + 17;
        } else if (std::strcmp(arg, "--test-signature") == 0) {
            if (++i >= argc) {
                throw std::invalid_argument("--test-signature requires an argument");
            }
            options.test_signature = argv[i];
        } else if (std::strcmp(arg, "--signature-granularity") == 0) {
            if (++i >= argc) {
                throw std::invalid_argument("--signature-granularity requires an argument");
            }
            options.signature_granularity = static_cast<uint32_t>(parse_u64(argv[i]));
        } else if (std::strcmp(arg, "--help") == 0 || std::strcmp(arg, "-h") == 0) {
            usage(argv[0]);
            std::exit(0);
        } else if (std::strcmp(arg, "--no-stats") == 0) {
            options.stats = false;
        } else if (arg[0] == '-') {
            throw std::invalid_argument(std::string("unknown option: ") + arg);
        } else {
            options.elf_path = arg;
            for (++i; i < argc; ++i) {
                options.target_args.emplace_back(argv[i]);
            }
            break;
        }
    }

    if (options.elf_path.empty()) {
        throw std::invalid_argument("missing ELF path");
    }
    if (options.cores < 1 || options.cores > sim::kMaxHarts) {
        throw std::invalid_argument("--cores must be between 1 and 16");
    }
    return options;
}

} // namespace

int main(int argc, char **argv) {
    try {
        Options options = parse_args(argc, argv);
        Simulator simulator(options);
        simulator.load_elf(options.elf_path);
        simulator.reset();
        sim::RunStats stats = simulator.run();
        if (!options.test_signature.empty()) {
            simulator.dump_signature(options.test_signature, options.signature_granularity);
        }
        if (options.stats) {
            double mhz = stats.sim_hz() / 1e6;
            std::fprintf(stderr,
                "-------------------------------\n"
                "retired = %-12" PRIu64 "\nmtime   = %-12" PRIu64
                "\nspeed   = %.0f Hz (%.2f MHz)\nwall    = %.3f s\n"
                "-------------------------------\n",
                stats.insns_retired, stats.cycles,
                stats.sim_hz(), mhz,
                stats.wall_seconds);
            std::fflush(stderr);
        }
        bool clean = (simulator.exit_code() == 0);
        return clean ? simulator.exit_code() : 1;
    } catch (const std::exception &ex) {
        std::cerr << "sim: " << ex.what() << '\n';
        return 1;
    }
}
