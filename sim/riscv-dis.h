// ============================================================================
// File: sim/riscv-dis.h
// Project: FreeRTOS-RISCV-SMP
// Description: RV64IMAC + Zicsr disassembler — public interface.
//
// Derived from jv32.dev/sim/riscv-dis.h, adapted for RV64 (64-bit PC,
// W-type instructions, RV64C compressed encoding changes).
// ============================================================================

#ifndef RISCV_DIS_H
#define RISCV_DIS_H

#include <cstdint>
#include <string>

// RISC-V Instruction Disassembler
// Supports RV64IMAC base ISA, M/A extensions, Zicsr, Zba/Zbb/Zbs/Zbc (B ext),
// Zicond, Zce (Zca+Zcb+Zcmp+Zcmt), Zfinx, Zdinx, Zhinx, Zfbfmin extensions.
//
// Derived from jv32.dev/sim/riscv-dis.h, adapted for RV64 (uint64_t PC,
// RV64I W-type instructions, RV64C compressed encoding changes).

class RiscvDisassembler {
public:
    RiscvDisassembler();

    // Disassemble a 32-bit (or 16-bit compressed) instruction at given PC.
    // Automatically detects compressed (16-bit) vs normal (32-bit) instructions.
    // Returns human-readable assembly string.
    std::string disassemble(uint32_t instr, uint64_t pc = 0);

private:
    // Instruction format decoders
    std::string decode_r_type(uint32_t instr, uint32_t opcode, uint32_t funct3, uint32_t funct7);
    std::string decode_i_type(uint32_t instr, uint32_t opcode, uint32_t funct3);
    std::string decode_s_type(uint32_t instr, uint32_t funct3);
    std::string decode_b_type(uint32_t instr, uint32_t funct3, uint64_t pc);
    std::string decode_u_type(uint32_t instr, uint32_t opcode);
    std::string decode_j_type(uint32_t instr, uint64_t pc);
    std::string decode_system(uint32_t instr, uint32_t funct3);
    std::string decode_amo(uint32_t instr, uint32_t funct3, uint32_t funct5);
    std::string decode_fp_r4(uint32_t instr, uint32_t opcode);  // FMADD/FMSUB/FNMADD/FNMSUB
    std::string decode_fp_op(uint32_t instr);                   // OP-FP (opcode 0x53)
    std::string decode_compressed(uint16_t instr, uint64_t pc);
    std::string decode_c_quadrant0(uint16_t instr);
    std::string decode_c_quadrant1(uint16_t instr, uint64_t pc);
    std::string decode_c_quadrant2(uint16_t instr);

    // Helper functions
    std::string reg_name(uint32_t reg);
    std::string c_reg_name(uint32_t reg);  // Compressed register (x8-x15)
    std::string csr_name(uint32_t csr);
    std::string rm_suffix(uint32_t rm);    // Rounding mode suffix (empty for rne/dyn)
    std::string format_address(uint64_t addr);
    int32_t sign_extend(uint32_t value, int bits);
};

#endif // RISCV_DIS_H
