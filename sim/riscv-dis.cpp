// ============================================================================
// File: sim/riscv-dis.cpp
// Project: FreeRTOS-RISCV-SMP
// Description: RV64IMAC + Zicsr + Zba/Zbb/Zbs + Zce + FP disassembler.
// Derived from jv32.dev/sim/riscv-dis.cpp, adapted for RV64:
//   - uint64_t PC throughout (branch/jump targets are 64-bit)
//   - Added RV64I LD/LWU/SD load-store
//   - Fixed 6-bit shift amounts for SLLI/SRLI/SRAI
//   - Added OP-IMM-32 (0x1B): ADDIW/SLLIW/SRLIW/SRAIW
//   - Added OP-32    (0x3B): ADDW/SUBW/SLLW/SRLW/SRAW + M-extension W variants
//   - RV64C: C.LD/C.SD (Q0), C.ADDIW (Q1), C.LDSP/C.SDSP (Q2)
// ============================================================================

#include "riscv-dis.h"
#include <sstream>
#include <iomanip>

RiscvDisassembler::RiscvDisassembler() {
}

std::string RiscvDisassembler::disassemble(uint32_t instr, uint64_t pc) {
    // Check if this is a compressed instruction (bottom 2 bits != 0b11)
    if ((instr & 0x3) != 0x3) {
        return decode_compressed((uint16_t)(instr & 0xFFFF), pc);
    }

    // Extract common fields for 32-bit instructions
    uint32_t opcode = instr & 0x7F;
    uint32_t funct3 = (instr >> 12) & 0x7;
    uint32_t funct7 = (instr >> 25) & 0x7F;
    uint32_t funct5 = (instr >> 27) & 0x1F;

    // Decode based on opcode
    switch (opcode) {
        case 0x37: // LUI
        case 0x17: // AUIPC
            return decode_u_type(instr, opcode);

        case 0x6F: // JAL
            return decode_j_type(instr, pc);

        case 0x67: // JALR
            return decode_i_type(instr, opcode, funct3);

        case 0x63: // BRANCH
            return decode_b_type(instr, funct3, pc);

        case 0x03: // LOAD
            return decode_i_type(instr, opcode, funct3);

        case 0x23: // STORE
            return decode_s_type(instr, funct3);

        case 0x13: // OP-IMM
            return decode_i_type(instr, opcode, funct3);

        case 0x33: // OP (R-type ALU, RV64: 64-bit operations)
            return decode_r_type(instr, opcode, funct3, funct7);

        case 0x1B: // OP-IMM-32 (RV64: ADDIW, SLLIW, SRLIW, SRAIW)
            return decode_i_type(instr, opcode, funct3);

        case 0x3B: // OP-32 (RV64: ADDW, SUBW, etc.)
            return decode_r_type(instr, opcode, funct3, funct7);

        case 0x0F: // FENCE
            if (funct3 == 0) return "fence";
            return "fence.i";

        case 0x0B: { // OPCODE_CUSTOM0: Zcmt cm.jt / cm.jalt
            uint32_t index   = (instr >> 20) & 0xFF;
            uint32_t rd_bits = (instr >> 7) & 0x1F;
            std::ostringstream oss0;
            if (rd_bits != 0)
                oss0 << "cm.jalt " << index;
            else
                oss0 << "cm.jt " << index;
            return oss0.str();
        }

        case 0x73: // SYSTEM (ECALL, EBREAK, CSR)
            return decode_system(instr, funct3);

        case 0x2F: // AMO (Atomic)
            return decode_amo(instr, funct3, funct5);

        case 0x43: // FMADD
        case 0x47: // FMSUB
        case 0x4B: // FNMSUB
        case 0x4F: // FNMADD
            return decode_fp_r4(instr, opcode);

        case 0x53: // OP-FP
            return decode_fp_op(instr);

        default:
            return "unknown";
    }
}

std::string RiscvDisassembler::decode_r_type(uint32_t instr, uint32_t opcode, uint32_t funct3, uint32_t funct7) {
    uint32_t rd  = (instr >> 7)  & 0x1F;
    uint32_t rs1 = (instr >> 15) & 0x1F;
    uint32_t rs2 = (instr >> 20) & 0x1F;

    std::ostringstream oss;
    std::string mnemonic;

    if (opcode == 0x33) { // OP — 64-bit arithmetic
        if (funct7 == 0x00) {
            switch (funct3) {
                case 0x0: mnemonic = "add";  break;
                case 0x1: mnemonic = "sll";  break;
                case 0x2: mnemonic = "slt";  break;
                case 0x3: mnemonic = "sltu"; break;
                case 0x4: mnemonic = "xor";  break;
                case 0x5: mnemonic = "srl";  break;
                case 0x6: mnemonic = "or";   break;
                case 0x7: mnemonic = "and";  break;
            }
        } else if (funct7 == 0x20) {
            if      (funct3 == 0x0) mnemonic = "sub";
            else if (funct3 == 0x5) mnemonic = "sra";
            // Zbb
            else if (funct3 == 0x4) mnemonic = "xnor";
            else if (funct3 == 0x6) mnemonic = "orn";
            else if (funct3 == 0x7) mnemonic = "andn";
        } else if (funct7 == 0x01) { // RV64M
            switch (funct3) {
                case 0x0: mnemonic = "mul";    break;
                case 0x1: mnemonic = "mulh";   break;
                case 0x2: mnemonic = "mulhsu"; break;
                case 0x3: mnemonic = "mulhu";  break;
                case 0x4: mnemonic = "div";    break;
                case 0x5: mnemonic = "divu";   break;
                case 0x6: mnemonic = "rem";    break;
                case 0x7: mnemonic = "remu";   break;
            }
        } else if (funct7 == 0x05) {
            switch (funct3) {
                case 0x1: mnemonic = "clmul";  break;
                case 0x2: mnemonic = "clmulr"; break;
                case 0x3: mnemonic = "clmulh"; break;
                case 0x4: mnemonic = "min";    break;
                case 0x5: mnemonic = "minu";   break;
                case 0x6: mnemonic = "max";    break;
                case 0x7: mnemonic = "maxu";   break;
            }
        } else if (funct7 == 0x04) { // Zbb
            if      (funct3 == 0x4 && rs2 == 0) mnemonic = "zext.h";
            else if (funct3 == 0x4) mnemonic = "pack";
            else if (funct3 == 0x7) mnemonic = "packh";
        } else if (funct7 == 0x30) { // Zbb rol/ror
            if      (funct3 == 0x1) mnemonic = "rol";
            else if (funct3 == 0x5) mnemonic = "ror";
        } else if (funct7 == 0x10) { // Zba sh*add
            switch (funct3) {
                case 0x2: mnemonic = "sh1add"; break;
                case 0x4: mnemonic = "sh2add"; break;
                case 0x6: mnemonic = "sh3add"; break;
            }
        } else if (funct7 == 0x24) { // Zbs bclr/bext
            if      (funct3 == 0x1) mnemonic = "bclr";
            else if (funct3 == 0x5) mnemonic = "bext";
        } else if (funct7 == 0x34) { // Zbs binv
            if (funct3 == 0x1) mnemonic = "binv";
        } else if (funct7 == 0x14) { // Zbs bset
            if (funct3 == 0x1) mnemonic = "bset";
        } else if (funct7 == 0x07) { // Zicond
            if      (funct3 == 0x5) mnemonic = "czero.eqz";
            else if (funct3 == 0x7) mnemonic = "czero.nez";
        }
    } else if (opcode == 0x3B) { // OP-32 — 32-bit arithmetic in RV64
        if (funct7 == 0x00) {
            switch (funct3) {
                case 0x0: mnemonic = "addw"; break;
                case 0x1: mnemonic = "sllw"; break;
                case 0x5: mnemonic = "srlw"; break;
            }
        } else if (funct7 == 0x20) {
            if      (funct3 == 0x0) mnemonic = "subw";
            else if (funct3 == 0x5) mnemonic = "sraw";
        } else if (funct7 == 0x01) { // RV64M W variants
            switch (funct3) {
                case 0x0: mnemonic = "mulw";  break;
                case 0x4: mnemonic = "divw";  break;
                case 0x5: mnemonic = "divuw"; break;
                case 0x6: mnemonic = "remw";  break;
                case 0x7: mnemonic = "remuw"; break;
            }
        }
    }

    if (mnemonic.empty()) {
        return "unknown";
    }

    oss << mnemonic << " " << reg_name(rd) << "," << reg_name(rs1) << "," << reg_name(rs2);
    return oss.str();
}

std::string RiscvDisassembler::decode_i_type(uint32_t instr, uint32_t opcode, uint32_t funct3) {
    uint32_t rd  = (instr >> 7)  & 0x1F;
    uint32_t rs1 = (instr >> 15) & 0x1F;
    int32_t  imm = sign_extend(instr >> 20, 12);

    std::ostringstream oss;
    std::string mnemonic;

    if (opcode == 0x03) { // LOAD
        switch (funct3) {
            case 0x0: mnemonic = "lb";  break;
            case 0x1: mnemonic = "lh";  break;
            case 0x2: mnemonic = "lw";  break;
            case 0x3: mnemonic = "ld";  break;  // RV64
            case 0x4: mnemonic = "lbu"; break;
            case 0x5: mnemonic = "lhu"; break;
            case 0x6: mnemonic = "lwu"; break;  // RV64
        }
        if (!mnemonic.empty()) {
            oss << mnemonic << " " << reg_name(rd) << "," << imm << "(" << reg_name(rs1) << ")";
            return oss.str();
        }
    } else if (opcode == 0x13) { // OP-IMM
        // RV64: shift amount is 6 bits (bits[25:20]), funct6 = bits[31:26]
        uint32_t shamt6 = (instr >> 20) & 0x3F;  // 6-bit shift amount for RV64
        uint32_t shamt5 = shamt6 & 0x1F;          // 5-bit for compatibility
        uint32_t funct6 = (instr >> 26) & 0x3F;   // upper 6 of funct7 (mask out shamt[5])

        switch (funct3) {
            case 0x0: mnemonic = "addi"; break;
            case 0x1:
                if (funct6 == 0x00) {
                    mnemonic = "slli"; imm = (int32_t)shamt6;
                } else if (funct6 == 0x18) { // Zbb: CLZ/CTZ/CPOP/SEXT.B/SEXT.H (funct7=0x30)
                    if (shamt5 == 0x00) { return "clz "    + reg_name(rd) + "," + reg_name(rs1); }
                    if (shamt5 == 0x01) { return "ctz "    + reg_name(rd) + "," + reg_name(rs1); }
                    if (shamt5 == 0x02) { return "cpop "   + reg_name(rd) + "," + reg_name(rs1); }
                    if (shamt5 == 0x04) { return "sext.b " + reg_name(rd) + "," + reg_name(rs1); }
                    if (shamt5 == 0x05) { return "sext.h " + reg_name(rd) + "," + reg_name(rs1); }
                } else if (funct6 == 0x12) { // Zbs BCLRI (funct7=0x24/0x25)
                    mnemonic = "bclri"; imm = (int32_t)shamt6;
                } else if (funct6 == 0x1A) { // Zbs BINVI (funct7=0x34/0x35)
                    mnemonic = "binvi"; imm = (int32_t)shamt6;
                } else if (funct6 == 0x0A) { // Zbs BSETI (funct7=0x14/0x15)
                    mnemonic = "bseti"; imm = (int32_t)shamt6;
                }
                break;
            case 0x2: mnemonic = "slti";  break;
            case 0x3: mnemonic = "sltiu"; break;
            case 0x4: mnemonic = "xori";  break;
            case 0x5:
                if (funct6 == 0x00) {
                    mnemonic = "srli"; imm = (int32_t)shamt6;
                } else if (funct6 == 0x10) { // SRAI (funct7=0x20/0x21)
                    mnemonic = "srai"; imm = (int32_t)shamt6;
                } else if (funct6 == 0x18) { // Zbb RORI (funct7=0x30/0x31)
                    mnemonic = "rori"; imm = (int32_t)shamt6;
                } else if ((funct6 & 0x3E) == 0x1A && shamt5 == 0x18) { // Zbb REV8
                    return "rev8 " + reg_name(rd) + "," + reg_name(rs1);
                } else if ((funct6 & 0x3E) == 0x0A && shamt5 == 0x07) { // Zbb ORC.B
                    return "orc.b " + reg_name(rd) + "," + reg_name(rs1);
                } else if (funct6 == 0x12) { // Zbs BEXTI (funct7=0x24/0x25)
                    mnemonic = "bexti"; imm = (int32_t)shamt6;
                }
                break;
            case 0x6: mnemonic = "ori";  break;
            case 0x7: mnemonic = "andi"; break;
        }

        if (!mnemonic.empty()) {
            oss << mnemonic << " " << reg_name(rd) << "," << reg_name(rs1) << "," << imm;
            return oss.str();
        }
    } else if (opcode == 0x67) { // JALR
        oss << "jalr " << reg_name(rd) << "," << reg_name(rs1) << "," << imm;
        return oss.str();
    } else if (opcode == 0x1B) { // OP-IMM-32 (RV64: W-type immediate ops)
        uint32_t shamt5 = (instr >> 20) & 0x1F;
        uint32_t funct7 = (instr >> 25) & 0x7F;
        switch (funct3) {
            case 0x0: mnemonic = "addiw"; break;
            case 0x1:
                if (funct7 == 0x00) { mnemonic = "slliw"; imm = (int32_t)shamt5; }
                break;
            case 0x5:
                if      (funct7 == 0x00) { mnemonic = "srliw"; imm = (int32_t)shamt5; }
                else if (funct7 == 0x20) { mnemonic = "sraiw"; imm = (int32_t)shamt5; }
                break;
        }
        if (!mnemonic.empty()) {
            if (funct3 == 0x0)
                oss << mnemonic << " " << reg_name(rd) << "," << reg_name(rs1) << "," << imm;
            else
                oss << mnemonic << " " << reg_name(rd) << "," << reg_name(rs1) << "," << imm;
            return oss.str();
        }
    }

    return "unknown";
}

std::string RiscvDisassembler::decode_s_type(uint32_t instr, uint32_t funct3) {
    uint32_t rs1 = (instr >> 15) & 0x1F;
    uint32_t rs2 = (instr >> 20) & 0x1F;
    int32_t  imm = sign_extend(((instr >> 25) << 5) | ((instr >> 7) & 0x1F), 12);

    std::ostringstream oss;
    std::string mnemonic;

    switch (funct3) {
        case 0x0: mnemonic = "sb"; break;
        case 0x1: mnemonic = "sh"; break;
        case 0x2: mnemonic = "sw"; break;
        case 0x3: mnemonic = "sd"; break;  // RV64
    }

    if (mnemonic.empty()) {
        return "unknown";
    }

    oss << mnemonic << " " << reg_name(rs2) << "," << imm << "(" << reg_name(rs1) << ")";
    return oss.str();
}

std::string RiscvDisassembler::decode_b_type(uint32_t instr, uint32_t funct3, uint64_t pc) {
    uint32_t rs1 = (instr >> 15) & 0x1F;
    uint32_t rs2 = (instr >> 20) & 0x1F;

    int32_t imm = sign_extend(
        ((instr >> 31) << 12) |
        (((instr >> 7)  & 0x1) << 11) |
        (((instr >> 25) & 0x3F) << 5) |
        (((instr >> 8)  & 0xF) << 1), 13);

    std::ostringstream oss;
    std::string mnemonic;

    switch (funct3) {
        case 0x0: mnemonic = "beq";  break;
        case 0x1: mnemonic = "bne";  break;
        case 0x4: mnemonic = "blt";  break;
        case 0x5: mnemonic = "bge";  break;
        case 0x6: mnemonic = "bltu"; break;
        case 0x7: mnemonic = "bgeu"; break;
    }

    if (mnemonic.empty()) {
        return "unknown";
    }

    uint64_t target = pc + (uint64_t)(int64_t)imm;
    oss << mnemonic << " " << reg_name(rs1) << "," << reg_name(rs2) << "," << format_address(target);
    return oss.str();
}

std::string RiscvDisassembler::decode_u_type(uint32_t instr, uint32_t opcode) {
    uint32_t rd  = (instr >> 7) & 0x1F;
    uint32_t imm = instr & 0xFFFFF000;

    std::ostringstream oss;

    if (opcode == 0x37) {
        oss << "lui " << reg_name(rd) << ",0x" << std::hex << (imm >> 12);
    } else if (opcode == 0x17) {
        oss << "auipc " << reg_name(rd) << ",0x" << std::hex << (imm >> 12);
    } else {
        return "unknown";
    }

    return oss.str();
}

std::string RiscvDisassembler::decode_j_type(uint32_t instr, uint64_t pc) {
    uint32_t rd = (instr >> 7) & 0x1F;

    int32_t imm = sign_extend(
        ((instr >> 31) << 20) |
        (((instr >> 12) & 0xFF) << 12) |
        (((instr >> 20) & 0x1) << 11) |
        (((instr >> 21) & 0x3FF) << 1), 21);

    std::ostringstream oss;
    uint64_t target = pc + (uint64_t)(int64_t)imm;
    oss << "jal " << reg_name(rd) << "," << format_address(target);
    return oss.str();
}

std::string RiscvDisassembler::decode_system(uint32_t instr, uint32_t funct3) {
    uint32_t rd   = (instr >> 7)  & 0x1F;
    uint32_t rs1  = (instr >> 15) & 0x1F;
    uint32_t csr  = instr >> 20;
    uint32_t zimm = rs1;

    std::ostringstream oss;

    if (funct3 == 0x0) {
        uint32_t imm = instr >> 20;
        if (imm == 0x0)   return "ecall";
        if (imm == 0x1)   return "ebreak";
        if (imm == 0x105) return "wfi";
        if (imm == 0x302) return "mret";
        if (imm == 0x102) return "sret";
        if (imm == 0x002) return "uret";
        return "unknown";
    }

    std::string mnemonic;
    bool is_imm = false;

    switch (funct3) {
        case 0x1: mnemonic = "csrrw";  break;
        case 0x2: mnemonic = "csrrs";  break;
        case 0x3: mnemonic = "csrrc";  break;
        case 0x5: mnemonic = "csrrwi"; is_imm = true; break;
        case 0x6: mnemonic = "csrrsi"; is_imm = true; break;
        case 0x7: mnemonic = "csrrci"; is_imm = true; break;
    }

    if (mnemonic.empty()) {
        return "unknown";
    }

    if (is_imm) {
        oss << mnemonic << " " << reg_name(rd) << "," << csr_name(csr) << "," << zimm;
    } else {
        oss << mnemonic << " " << reg_name(rd) << "," << csr_name(csr) << "," << reg_name(rs1);
    }

    return oss.str();
}

std::string RiscvDisassembler::decode_amo(uint32_t instr, uint32_t funct3, uint32_t funct5) {
    uint32_t rd  = (instr >> 7)  & 0x1F;
    uint32_t rs1 = (instr >> 15) & 0x1F;
    uint32_t rs2 = (instr >> 20) & 0x1F;
    uint32_t aq  = (instr >> 26) & 0x1;
    uint32_t rl  = (instr >> 27) & 0x1;

    std::ostringstream oss;
    std::string mnemonic;
    std::string suffix;

    if      (funct3 == 0x2) suffix = ".w";
    else if (funct3 == 0x3) suffix = ".d";
    else return "unknown";

    if      (aq && rl) suffix += ".aqrl";
    else if (aq)       suffix += ".aq";
    else if (rl)       suffix += ".rl";

    switch (funct5) {
        case 0x02: mnemonic = "lr";      break;
        case 0x03: mnemonic = "sc";      break;
        case 0x01: mnemonic = "amoswap"; break;
        case 0x00: mnemonic = "amoadd";  break;
        case 0x04: mnemonic = "amoxor";  break;
        case 0x0C: mnemonic = "amoand";  break;
        case 0x08: mnemonic = "amoor";   break;
        case 0x10: mnemonic = "amomin";  break;
        case 0x14: mnemonic = "amomax";  break;
        case 0x18: mnemonic = "amominu"; break;
        case 0x1C: mnemonic = "amomaxu"; break;
    }

    if (mnemonic.empty()) {
        return "unknown";
    }

    if (funct5 == 0x02) {
        oss << mnemonic << suffix << " " << reg_name(rd) << ",(" << reg_name(rs1) << ")";
    } else {
        oss << mnemonic << suffix << " " << reg_name(rd) << "," << reg_name(rs2) << ",(" << reg_name(rs1) << ")";
    }

    return oss.str();
}

std::string RiscvDisassembler::rm_suffix(uint32_t rm) {
    switch (rm) {
        case 1: return ",rtz";
        case 2: return ",rdn";
        case 3: return ",rup";
        case 4: return ",rmm";
        default: return "";  // rne(0) and dyn(7) are implicit
    }
}

std::string RiscvDisassembler::decode_fp_r4(uint32_t instr, uint32_t opcode) {
    uint32_t rd  = (instr >> 7)  & 0x1F;
    uint32_t rm  = (instr >> 12) & 0x7;
    uint32_t rs1 = (instr >> 15) & 0x1F;
    uint32_t rs2 = (instr >> 20) & 0x1F;
    uint32_t fmt = (instr >> 25) & 0x3;
    uint32_t rs3 = (instr >> 27) & 0x1F;

    const char* suf;
    switch (fmt) {
        case 0: suf = ".s"; break;
        case 1: suf = ".d"; break;
        case 2: suf = ".h"; break;
        default: return "unknown";
    }

    const char* mnem;
    switch (opcode) {
        case 0x43: mnem = "fmadd";  break;
        case 0x47: mnem = "fmsub";  break;
        case 0x4B: mnem = "fnmsub"; break;
        case 0x4F: mnem = "fnmadd"; break;
        default: return "unknown";
    }

    std::ostringstream oss;
    oss << mnem << suf << " " << reg_name(rd) << "," << reg_name(rs1)
        << "," << reg_name(rs2) << "," << reg_name(rs3) << rm_suffix(rm);
    return oss.str();
}

std::string RiscvDisassembler::decode_fp_op(uint32_t instr) {
    uint32_t rd     = (instr >> 7)  & 0x1F;
    uint32_t funct3 = (instr >> 12) & 0x7;
    uint32_t rs1    = (instr >> 15) & 0x1F;
    uint32_t rs2    = (instr >> 20) & 0x1F;
    uint32_t funct7 = (instr >> 25) & 0x7F;
    uint32_t rm     = funct3;

    std::ostringstream oss;

    switch (funct7) {
        case 0x00: oss << "fadd.s "  << reg_name(rd) << "," << reg_name(rs1) << "," << reg_name(rs2) << rm_suffix(rm); return oss.str();
        case 0x04: oss << "fsub.s "  << reg_name(rd) << "," << reg_name(rs1) << "," << reg_name(rs2) << rm_suffix(rm); return oss.str();
        case 0x08: oss << "fmul.s "  << reg_name(rd) << "," << reg_name(rs1) << "," << reg_name(rs2) << rm_suffix(rm); return oss.str();
        case 0x0C: oss << "fdiv.s "  << reg_name(rd) << "," << reg_name(rs1) << "," << reg_name(rs2) << rm_suffix(rm); return oss.str();
        case 0x2C: oss << "fsqrt.s " << reg_name(rd) << "," << reg_name(rs1) << rm_suffix(rm); return oss.str();
        case 0x10:
            if      (funct3 == 0) { oss << "fsgnj.s "  << reg_name(rd) << "," << reg_name(rs1) << "," << reg_name(rs2); return oss.str(); }
            else if (funct3 == 1) { oss << "fsgnjn.s " << reg_name(rd) << "," << reg_name(rs1) << "," << reg_name(rs2); return oss.str(); }
            else if (funct3 == 2) { oss << "fsgnjx.s " << reg_name(rd) << "," << reg_name(rs1) << "," << reg_name(rs2); return oss.str(); }
            return "unknown";
        case 0x14:
            if      (funct3 == 0) { oss << "fmin.s " << reg_name(rd) << "," << reg_name(rs1) << "," << reg_name(rs2); return oss.str(); }
            else if (funct3 == 1) { oss << "fmax.s " << reg_name(rd) << "," << reg_name(rs1) << "," << reg_name(rs2); return oss.str(); }
            return "unknown";
        case 0x50:
            if      (funct3 == 2) { oss << "feq.s " << reg_name(rd) << "," << reg_name(rs1) << "," << reg_name(rs2); return oss.str(); }
            else if (funct3 == 1) { oss << "flt.s " << reg_name(rd) << "," << reg_name(rs1) << "," << reg_name(rs2); return oss.str(); }
            else if (funct3 == 0) { oss << "fle.s " << reg_name(rd) << "," << reg_name(rs1) << "," << reg_name(rs2); return oss.str(); }
            return "unknown";
        case 0x60:
            if      (rs2 == 0) { oss << "fcvt.w.s "  << reg_name(rd) << "," << reg_name(rs1) << rm_suffix(rm); return oss.str(); }
            else if (rs2 == 1) { oss << "fcvt.wu.s " << reg_name(rd) << "," << reg_name(rs1) << rm_suffix(rm); return oss.str(); }
            return "unknown";
        case 0x68:
            if      (rs2 == 0) { oss << "fcvt.s.w "  << reg_name(rd) << "," << reg_name(rs1) << rm_suffix(rm); return oss.str(); }
            else if (rs2 == 1) { oss << "fcvt.s.wu " << reg_name(rd) << "," << reg_name(rs1) << rm_suffix(rm); return oss.str(); }
            return "unknown";
        case 0x70:
            if (rs2 == 0) {
                if      (funct3 == 0) { oss << "fmv.x.w "  << reg_name(rd) << "," << reg_name(rs1); return oss.str(); }
                else if (funct3 == 1) { oss << "fclass.s " << reg_name(rd) << "," << reg_name(rs1); return oss.str(); }
            }
            return "unknown";
        case 0x78:
            if (rs2 == 0 && funct3 == 0) { oss << "fmv.w.x " << reg_name(rd) << "," << reg_name(rs1); return oss.str(); }
            return "unknown";

        case 0x01: oss << "fadd.d "  << reg_name(rd) << "," << reg_name(rs1) << "," << reg_name(rs2) << rm_suffix(rm); return oss.str();
        case 0x05: oss << "fsub.d "  << reg_name(rd) << "," << reg_name(rs1) << "," << reg_name(rs2) << rm_suffix(rm); return oss.str();
        case 0x09: oss << "fmul.d "  << reg_name(rd) << "," << reg_name(rs1) << "," << reg_name(rs2) << rm_suffix(rm); return oss.str();
        case 0x0D: oss << "fdiv.d "  << reg_name(rd) << "," << reg_name(rs1) << "," << reg_name(rs2) << rm_suffix(rm); return oss.str();
        case 0x2D: oss << "fsqrt.d " << reg_name(rd) << "," << reg_name(rs1) << rm_suffix(rm); return oss.str();
        case 0x11:
            if      (funct3 == 0) { oss << "fsgnj.d "  << reg_name(rd) << "," << reg_name(rs1) << "," << reg_name(rs2); return oss.str(); }
            else if (funct3 == 1) { oss << "fsgnjn.d " << reg_name(rd) << "," << reg_name(rs1) << "," << reg_name(rs2); return oss.str(); }
            else if (funct3 == 2) { oss << "fsgnjx.d " << reg_name(rd) << "," << reg_name(rs1) << "," << reg_name(rs2); return oss.str(); }
            return "unknown";
        case 0x15:
            if      (funct3 == 0) { oss << "fmin.d " << reg_name(rd) << "," << reg_name(rs1) << "," << reg_name(rs2); return oss.str(); }
            else if (funct3 == 1) { oss << "fmax.d " << reg_name(rd) << "," << reg_name(rs1) << "," << reg_name(rs2); return oss.str(); }
            return "unknown";
        case 0x51:
            if      (funct3 == 2) { oss << "feq.d " << reg_name(rd) << "," << reg_name(rs1) << "," << reg_name(rs2); return oss.str(); }
            else if (funct3 == 1) { oss << "flt.d " << reg_name(rd) << "," << reg_name(rs1) << "," << reg_name(rs2); return oss.str(); }
            else if (funct3 == 0) { oss << "fle.d " << reg_name(rd) << "," << reg_name(rs1) << "," << reg_name(rs2); return oss.str(); }
            return "unknown";
        case 0x61:
            if      (rs2 == 0) { oss << "fcvt.w.d "  << reg_name(rd) << "," << reg_name(rs1) << rm_suffix(rm); return oss.str(); }
            else if (rs2 == 1) { oss << "fcvt.wu.d " << reg_name(rd) << "," << reg_name(rs1) << rm_suffix(rm); return oss.str(); }
            return "unknown";
        case 0x69:
            if      (rs2 == 0) { oss << "fcvt.d.w "  << reg_name(rd) << "," << reg_name(rs1) << rm_suffix(rm); return oss.str(); }
            else if (rs2 == 1) { oss << "fcvt.d.wu " << reg_name(rd) << "," << reg_name(rs1) << rm_suffix(rm); return oss.str(); }
            return "unknown";
        case 0x71:
            if (rs2 == 0 && funct3 == 1) { oss << "fclass.d " << reg_name(rd) << "," << reg_name(rs1); return oss.str(); }
            return "unknown";
        case 0x21:
            if (rs2 == 0) { oss << "fcvt.d.s " << reg_name(rd) << "," << reg_name(rs1) << rm_suffix(rm); return oss.str(); }
            return "unknown";

        case 0x02: oss << "fadd.h "  << reg_name(rd) << "," << reg_name(rs1) << "," << reg_name(rs2) << rm_suffix(rm); return oss.str();
        case 0x06: oss << "fsub.h "  << reg_name(rd) << "," << reg_name(rs1) << "," << reg_name(rs2) << rm_suffix(rm); return oss.str();
        case 0x0A: oss << "fmul.h "  << reg_name(rd) << "," << reg_name(rs1) << "," << reg_name(rs2) << rm_suffix(rm); return oss.str();
        case 0x0E: oss << "fdiv.h "  << reg_name(rd) << "," << reg_name(rs1) << "," << reg_name(rs2) << rm_suffix(rm); return oss.str();
        case 0x2E: oss << "fsqrt.h " << reg_name(rd) << "," << reg_name(rs1) << rm_suffix(rm); return oss.str();
        case 0x12:
            if      (funct3 == 0) { oss << "fsgnj.h "  << reg_name(rd) << "," << reg_name(rs1) << "," << reg_name(rs2); return oss.str(); }
            else if (funct3 == 1) { oss << "fsgnjn.h " << reg_name(rd) << "," << reg_name(rs1) << "," << reg_name(rs2); return oss.str(); }
            else if (funct3 == 2) { oss << "fsgnjx.h " << reg_name(rd) << "," << reg_name(rs1) << "," << reg_name(rs2); return oss.str(); }
            return "unknown";
        case 0x16:
            if      (funct3 == 0) { oss << "fmin.h " << reg_name(rd) << "," << reg_name(rs1) << "," << reg_name(rs2); return oss.str(); }
            else if (funct3 == 1) { oss << "fmax.h " << reg_name(rd) << "," << reg_name(rs1) << "," << reg_name(rs2); return oss.str(); }
            return "unknown";
        case 0x52:
            if      (funct3 == 2) { oss << "feq.h " << reg_name(rd) << "," << reg_name(rs1) << "," << reg_name(rs2); return oss.str(); }
            else if (funct3 == 1) { oss << "flt.h " << reg_name(rd) << "," << reg_name(rs1) << "," << reg_name(rs2); return oss.str(); }
            else if (funct3 == 0) { oss << "fle.h " << reg_name(rd) << "," << reg_name(rs1) << "," << reg_name(rs2); return oss.str(); }
            return "unknown";
        case 0x62:
            if      (rs2 == 0) { oss << "fcvt.w.h "  << reg_name(rd) << "," << reg_name(rs1) << rm_suffix(rm); return oss.str(); }
            else if (rs2 == 1) { oss << "fcvt.wu.h " << reg_name(rd) << "," << reg_name(rs1) << rm_suffix(rm); return oss.str(); }
            return "unknown";
        case 0x6A:
            if      (rs2 == 0) { oss << "fcvt.h.w "  << reg_name(rd) << "," << reg_name(rs1) << rm_suffix(rm); return oss.str(); }
            else if (rs2 == 1) { oss << "fcvt.h.wu " << reg_name(rd) << "," << reg_name(rs1) << rm_suffix(rm); return oss.str(); }
            return "unknown";
        case 0x72:
            if (rs2 == 0 && funct3 == 1) { oss << "fclass.h " << reg_name(rd) << "," << reg_name(rs1); return oss.str(); }
            return "unknown";
        case 0x22:
            if (rs2 == 0) { oss << "fcvt.h.s " << reg_name(rd) << "," << reg_name(rs1) << rm_suffix(rm); return oss.str(); }
            return "unknown";
        case 0x20:
            if      (rs2 == 1) { oss << "fcvt.s.d "    << reg_name(rd) << "," << reg_name(rs1) << rm_suffix(rm); return oss.str(); }
            else if (rs2 == 2) { oss << "fcvt.s.h "    << reg_name(rd) << "," << reg_name(rs1) << rm_suffix(rm); return oss.str(); }
            else if (rs2 == 6) { oss << "fcvt.s.bf16 " << reg_name(rd) << "," << reg_name(rs1) << rm_suffix(rm); return oss.str(); }
            return "unknown";
        case 0x44:
            if (rs2 == 0) { oss << "fcvt.bf16.s " << reg_name(rd) << "," << reg_name(rs1) << rm_suffix(rm); return oss.str(); }
            return "unknown";

        default:
            return "unknown";
    }
}

std::string RiscvDisassembler::reg_name(uint32_t reg) {
    static const char* abi_names[] = {
        "zero", "ra",  "sp",  "gp",  "tp",  "t0",  "t1",  "t2",
        "s0",   "s1",  "a0",  "a1",  "a2",  "a3",  "a4",  "a5",
        "a6",   "a7",  "s2",  "s3",  "s4",  "s5",  "s6",  "s7",
        "s8",   "s9",  "s10", "s11", "t3",  "t4",  "t5",  "t6"
    };
    if (reg < 32) return abi_names[reg];
    return "x?";
}

std::string RiscvDisassembler::csr_name(uint32_t csr) {
    switch (csr) {
        case 0x001: return "fflags";
        case 0x002: return "frm";
        case 0x003: return "fcsr";
        case 0x017: return "jvt";
        case 0xF11: return "mvendorid";
        case 0xF12: return "marchid";
        case 0xF13: return "mimpid";
        case 0xF14: return "mhartid";
        case 0x300: return "mstatus";
        case 0x301: return "misa";
        case 0x302: return "medeleg";
        case 0x303: return "mideleg";
        case 0x304: return "mie";
        case 0x305: return "mtvec";
        case 0x306: return "mcounteren";
        case 0x310: return "mstatush";
        case 0x320: return "mcountinhibit";
        case 0x340: return "mscratch";
        case 0x341: return "mepc";
        case 0x342: return "mcause";
        case 0x343: return "mtval";
        case 0x344: return "mip";
        case 0x3A0: return "pmpcfg0";
        case 0x3A1: return "pmpcfg1";
        case 0x3A2: return "pmpcfg2";
        case 0x3A3: return "pmpcfg3";
        case 0x3B0: return "pmpaddr0";
        case 0x3B1: return "pmpaddr1";
        case 0x3B2: return "pmpaddr2";
        case 0x3B3: return "pmpaddr3";
        case 0x3B4: return "pmpaddr4";
        case 0x3B5: return "pmpaddr5";
        case 0x3B6: return "pmpaddr6";
        case 0x3B7: return "pmpaddr7";
        case 0x3B8: return "pmpaddr8";
        case 0x3B9: return "pmpaddr9";
        case 0x3BA: return "pmpaddr10";
        case 0x3BB: return "pmpaddr11";
        case 0x3BC: return "pmpaddr12";
        case 0x3BD: return "pmpaddr13";
        case 0x3BE: return "pmpaddr14";
        case 0x3BF: return "pmpaddr15";
        case 0xB00: return "mcycle";
        case 0xB02: return "minstret";
        case 0xB80: return "mcycleh";
        case 0xB82: return "minstreth";
        case 0xC00: return "cycle";
        case 0xC01: return "time";
        case 0xC02: return "instret";
        case 0xC80: return "cycleh";
        case 0xC81: return "timeh";
        case 0xC82: return "instreth";
        default: {
            std::ostringstream oss;
            oss << "0x" << std::hex << csr;
            return oss.str();
        }
    }
}

std::string RiscvDisassembler::format_address(uint64_t addr) {
    std::ostringstream oss;
    oss << "0x" << std::hex << addr;
    return oss.str();
}

int32_t RiscvDisassembler::sign_extend(uint32_t value, int bits) {
    uint32_t sign_bit = 1U << (bits - 1);
    if (value & sign_bit) {
        uint32_t mask = ~((1U << bits) - 1);
        return (int32_t)(value | mask);
    }
    return (int32_t)value;
}

std::string RiscvDisassembler::c_reg_name(uint32_t reg) {
    return reg_name(reg + 8);
}

std::string RiscvDisassembler::decode_compressed(uint16_t instr, uint64_t pc) {
    uint32_t quadrant = instr & 0x3;
    switch (quadrant) {
        case 0: return decode_c_quadrant0(instr);
        case 1: return decode_c_quadrant1(instr, pc);
        case 2: return decode_c_quadrant2(instr);
        default: return "unknown";
    }
}

std::string RiscvDisassembler::decode_c_quadrant0(uint16_t instr) {
    uint32_t funct3    = (instr >> 13) & 0x7;
    uint32_t rd_rs2_p  = (instr >> 2)  & 0x7;
    uint32_t rs1_p     = (instr >> 7)  & 0x7;

    std::ostringstream oss;

    switch (funct3) {
        case 0x0: { // C.ADDI4SPN
            uint32_t nzuimm = ((instr >> 7) & 0x30) | ((instr >> 1) & 0x3C0) |
                              ((instr >> 4) & 0x4)   | ((instr >> 2) & 0x8);
            if (nzuimm == 0) return "illegal";
            oss << "c.addi4spn " << c_reg_name(rd_rs2_p) << ",sp," << nzuimm;
            return oss.str();
        }
        case 0x1: return "c.fld";  // C.FLD (FP) — not RV64C replacement
        case 0x2: { // C.LW
            uint32_t uimm = ((instr >> 7) & 0x38) | ((instr >> 4) & 0x4) | ((instr << 1) & 0x40);
            oss << "c.lw " << c_reg_name(rd_rs2_p) << "," << uimm << "(" << c_reg_name(rs1_p) << ")";
            return oss.str();
        }
        case 0x3: { // C.LD (RV64 — replaces C.FLW)
            uint32_t uimm = ((instr >> 7) & 0x38) | ((instr << 1) & 0xC0);
            oss << "c.ld " << c_reg_name(rd_rs2_p) << "," << uimm << "(" << c_reg_name(rs1_p) << ")";
            return oss.str();
        }
        case 0x4: { // Zcb: c.lbu / c.lhu / c.lh / c.sb / c.sh
            uint32_t ci_11_10 = (instr >> 10) & 0x3;
            uint32_t ci_6_5   = (instr >> 5)  & 0x3;
            uint32_t rd_p     = (instr >> 2)  & 0x7;
            if (ci_11_10 == 0x0 && ci_6_5 == 0x0) {
                uint32_t uimm = ((instr >> 4) & 0x2) | ((instr >> 6) & 0x1);
                oss << "c.lbu " << c_reg_name(rd_p) << "," << uimm << "(" << c_reg_name(rs1_p) << ")";
            } else if (ci_11_10 == 0x0 && ci_6_5 == 0x1) {
                uint32_t uimm = ((instr >> 4) & 0x2);
                oss << "c.lhu " << c_reg_name(rd_p) << "," << uimm << "(" << c_reg_name(rs1_p) << ")";
            } else if (ci_11_10 == 0x0 && ci_6_5 == 0x2) {
                uint32_t uimm = ((instr >> 4) & 0x2);
                oss << "c.lh " << c_reg_name(rd_p) << "," << uimm << "(" << c_reg_name(rs1_p) << ")";
            } else if (ci_11_10 == 0x1 && ci_6_5 == 0x0) {
                uint32_t uimm = ((instr >> 4) & 0x2) | ((instr >> 6) & 0x1);
                oss << "c.sb " << c_reg_name(rd_p) << "," << uimm << "(" << c_reg_name(rs1_p) << ")";
            } else if (ci_11_10 == 0x1 && ci_6_5 == 0x1) {
                uint32_t uimm = ((instr >> 4) & 0x2);
                oss << "c.sh " << c_reg_name(rd_p) << "," << uimm << "(" << c_reg_name(rs1_p) << ")";
            } else {
                return "unknown";
            }
            return oss.str();
        }
        case 0x5: return "c.fsd";  // C.FSD (FP)
        case 0x6: { // C.SW
            uint32_t uimm = ((instr >> 7) & 0x38) | ((instr >> 4) & 0x4) | ((instr << 1) & 0x40);
            oss << "c.sw " << c_reg_name(rd_rs2_p) << "," << uimm << "(" << c_reg_name(rs1_p) << ")";
            return oss.str();
        }
        case 0x7: { // C.SD (RV64 — replaces C.FSW)
            uint32_t uimm = ((instr >> 7) & 0x38) | ((instr << 1) & 0xC0);
            oss << "c.sd " << c_reg_name(rd_rs2_p) << "," << uimm << "(" << c_reg_name(rs1_p) << ")";
            return oss.str();
        }
        default:
            return "unknown";
    }
}

std::string RiscvDisassembler::decode_c_quadrant1(uint16_t instr, uint64_t pc) {
    uint32_t funct3  = (instr >> 13) & 0x7;
    uint32_t rd_rs1  = (instr >> 7)  & 0x1F;

    std::ostringstream oss;

    switch (funct3) {
        case 0x0: { // C.ADDI / C.NOP
            int32_t nzimm = sign_extend(((instr >> 7) & 0x20) | ((instr >> 2) & 0x1F), 6);
            if (rd_rs1 == 0 && nzimm == 0) return "c.nop";
            if (rd_rs1 == 0) return "illegal";
            oss << "c.addi " << reg_name(rd_rs1) << "," << nzimm;
            return oss.str();
        }
        case 0x1: { // C.ADDIW (RV64 — replaces C.JAL of RV32)
            int32_t imm = sign_extend(((instr >> 7) & 0x20) | ((instr >> 2) & 0x1F), 6);
            if (rd_rs1 == 0) return "illegal";
            oss << "c.addiw " << reg_name(rd_rs1) << "," << imm;
            return oss.str();
        }
        case 0x2: { // C.LI
            int32_t imm = sign_extend(((instr >> 7) & 0x20) | ((instr >> 2) & 0x1F), 6);
            if (rd_rs1 == 0) return "illegal";
            oss << "c.li " << reg_name(rd_rs1) << "," << imm;
            return oss.str();
        }
        case 0x3: { // C.ADDI16SP / C.LUI
            if (rd_rs1 == 2) {
                int32_t nzimm = sign_extend(
                    ((instr >> 3) & 0x200) | ((instr >> 2) & 0x10) | ((instr << 1) & 0x40) |
                    ((instr << 4) & 0x180) | ((instr << 3) & 0x20), 10);
                if (nzimm == 0) return "illegal";
                oss << "c.addi16sp sp," << nzimm;
                return oss.str();
            } else {
                int32_t nzimm = sign_extend(((instr >> 7) & 0x20) | ((instr >> 2) & 0x1F), 6);
                if (rd_rs1 == 0 || nzimm == 0) return "illegal";
                oss << "c.lui " << reg_name(rd_rs1) << ",0x" << std::hex << (nzimm & 0x1F);
                return oss.str();
            }
        }
        case 0x4: { // Arithmetic
            uint32_t funct2    = (instr >> 10) & 0x3;
            uint32_t rd_rs1_p  = (instr >> 7)  & 0x7;
            uint32_t rs2_p     = (instr >> 2)  & 0x7;

            if (funct2 == 0x0) { // C.SRLI
                uint32_t shamt = ((instr >> 7) & 0x20) | ((instr >> 2) & 0x1F);
                oss << "c.srli " << c_reg_name(rd_rs1_p) << "," << shamt;
                return oss.str();
            } else if (funct2 == 0x1) { // C.SRAI
                uint32_t shamt = ((instr >> 7) & 0x20) | ((instr >> 2) & 0x1F);
                oss << "c.srai " << c_reg_name(rd_rs1_p) << "," << shamt;
                return oss.str();
            } else if (funct2 == 0x2) { // C.ANDI
                int32_t imm = sign_extend(((instr >> 7) & 0x20) | ((instr >> 2) & 0x1F), 6);
                oss << "c.andi " << c_reg_name(rd_rs1_p) << "," << imm;
                return oss.str();
            } else if (funct2 == 0x3) {
                uint32_t funct1     = (instr >> 12) & 0x1;
                uint32_t funct2_low = (instr >> 5)  & 0x3;

                if (funct1 == 0) {
                    if      (funct2_low == 0x0) { oss << "c.sub " << c_reg_name(rd_rs1_p) << "," << c_reg_name(rs2_p); }
                    else if (funct2_low == 0x1) { oss << "c.xor " << c_reg_name(rd_rs1_p) << "," << c_reg_name(rs2_p); }
                    else if (funct2_low == 0x2) { oss << "c.or  " << c_reg_name(rd_rs1_p) << "," << c_reg_name(rs2_p); }
                    else if (funct2_low == 0x3) { oss << "c.and " << c_reg_name(rd_rs1_p) << "," << c_reg_name(rs2_p); }
                    else return "unknown";
                } else { // funct1==1: RV64 c.subw/c.addw + Zcb unary
                    uint32_t f2_low = (instr >> 5) & 0x3;
                    if      (f2_low == 0x0) { oss << "c.subw " << c_reg_name(rd_rs1_p) << "," << c_reg_name(rs2_p); }
                    else if (f2_low == 0x1) { oss << "c.addw " << c_reg_name(rd_rs1_p) << "," << c_reg_name(rs2_p); }
                    else if (f2_low == 0x2) { oss << "c.mul " << c_reg_name(rd_rs1_p) << "," << c_reg_name(rs2_p); }
                    else if (f2_low == 0x3) { // unary
                        uint32_t sel = (instr >> 2) & 0x7;
                        if      (sel == 0) oss << "c.zext.b " << c_reg_name(rd_rs1_p);
                        else if (sel == 1) oss << "c.sext.b " << c_reg_name(rd_rs1_p);
                        else if (sel == 2) oss << "c.zext.h " << c_reg_name(rd_rs1_p);
                        else if (sel == 3) oss << "c.sext.h " << c_reg_name(rd_rs1_p);
                        else if (sel == 4) oss << "c.zext.w " << c_reg_name(rd_rs1_p);
                        else if (sel == 5) oss << "c.not "    << c_reg_name(rd_rs1_p);
                        else return "unknown";
                    } else {
                        return "unknown";
                    }
                }
                return oss.str();
            }
            return "unknown";
        }
        case 0x5: { // C.J
            int32_t imm = sign_extend(
                ((instr >> 1) & 0x800) | ((instr >> 7) & 0x10) | ((instr >> 1) & 0x300) |
                ((instr << 2) & 0x400) | ((instr >> 1) & 0x40) | ((instr << 1) & 0x80) |
                ((instr >> 2) & 0xE)   | ((instr << 3) & 0x20), 12);
            uint64_t target = pc + (uint64_t)(int64_t)imm;
            oss << "c.j " << format_address(target);
            return oss.str();
        }
        case 0x6: { // C.BEQZ
            uint32_t rs1_p = (instr >> 7) & 0x7;
            int32_t imm = sign_extend(
                ((instr >> 4) & 0x100) | ((instr >> 7) & 0x18) | ((instr << 1) & 0xC0) |
                ((instr >> 2) & 0x6)   | ((instr << 3) & 0x20), 9);
            uint64_t target = pc + (uint64_t)(int64_t)imm;
            oss << "c.beqz " << c_reg_name(rs1_p) << "," << format_address(target);
            return oss.str();
        }
        case 0x7: { // C.BNEZ
            uint32_t rs1_p = (instr >> 7) & 0x7;
            int32_t imm = sign_extend(
                ((instr >> 4) & 0x100) | ((instr >> 7) & 0x18) | ((instr << 1) & 0xC0) |
                ((instr >> 2) & 0x6)   | ((instr << 3) & 0x20), 9);
            uint64_t target = pc + (uint64_t)(int64_t)imm;
            oss << "c.bnez " << c_reg_name(rs1_p) << "," << format_address(target);
            return oss.str();
        }
        default:
            return "unknown";
    }
}

std::string RiscvDisassembler::decode_c_quadrant2(uint16_t instr) {
    uint32_t funct3 = (instr >> 13) & 0x7;
    uint32_t rd_rs1 = (instr >> 7)  & 0x1F;
    uint32_t rs2    = (instr >> 2)  & 0x1F;

    std::ostringstream oss;

    switch (funct3) {
        case 0x0: { // C.SLLI
            uint32_t shamt = ((instr >> 7) & 0x20) | ((instr >> 2) & 0x1F);
            if (rd_rs1 == 0 || shamt == 0) return "illegal";
            oss << "c.slli " << reg_name(rd_rs1) << "," << shamt;
            return oss.str();
        }
        case 0x1: return "c.fldsp";  // C.FLDSP (FP)
        case 0x2: { // C.LWSP
            uint32_t uimm = ((instr >> 7) & 0x20) | ((instr >> 2) & 0x1C) | ((instr << 4) & 0xC0);
            if (rd_rs1 == 0) return "illegal";
            oss << "c.lwsp " << reg_name(rd_rs1) << "," << uimm << "(sp)";
            return oss.str();
        }
        case 0x3: { // C.LDSP (RV64 — replaces C.FLWSP)
            // offset = {instr[4:2], instr[12], instr[6:5], 3'b000}
            uint32_t uimm = ((instr >> 7) & 0x20)  // o[5] = instr[12]
                          | ((instr >> 2) & 0x18)   // o[4:3] = instr[6:5]
                          | ((instr << 4) & 0x1C0); // o[8:6] = instr[4:2]
            if (rd_rs1 == 0) return "illegal";
            oss << "c.ldsp " << reg_name(rd_rs1) << "," << uimm << "(sp)";
            return oss.str();
        }
        case 0x4: { // C.JR / C.MV / C.EBREAK / C.JALR / C.ADD
            uint32_t funct1 = (instr >> 12) & 0x1;
            if (funct1 == 0) {
                if (rs2 == 0) {
                    if (rd_rs1 == 0) return "illegal";
                    oss << "c.jr " << reg_name(rd_rs1);
                } else {
                    oss << "c.mv " << reg_name(rd_rs1) << "," << reg_name(rs2);
                }
            } else {
                if (rd_rs1 == 0 && rs2 == 0) return "c.ebreak";
                else if (rs2 == 0) oss << "c.jalr " << reg_name(rd_rs1);
                else oss << "c.add " << reg_name(rd_rs1) << "," << reg_name(rs2);
            }
            return oss.str();
        }
        case 0x5: { // Zcmt cm.jt/cm.jalt | Zcmp push/pop
            uint32_t ci_12_10 = (instr >> 10) & 0x7;
            if (ci_12_10 == 0x0) {
                uint32_t index = (instr >> 2) & 0xFF;
                if (index >= 32) oss << "cm.jalt " << index;
                else             oss << "cm.jt " << index;
                return oss.str();
            }
            if (ci_12_10 == 0x3) {
                uint32_t ci_6_5 = (instr >> 5) & 0x3;
                uint32_t r1s    = (instr >> 7)  & 0x7;
                uint32_t r2s    = (instr >> 2)  & 0x7;
                static const char* sn[8] = {"s0","s1","s2","s3","s4","s5","s6","s7"};
                if      (ci_6_5 == 0x1) oss << "cm.mvsa01 " << sn[r1s] << "," << sn[r2s];
                else if (ci_6_5 == 0x3) oss << "cm.mva01s " << sn[r1s] << "," << sn[r2s];
                else return "unknown";
                return oss.str();
            }
            if (((instr >> 12) & 1) && ((instr >> 11) & 1) && !((instr >> 8) & 1)) {
                uint32_t ci_10_9 = (instr >> 9) & 0x3;
                uint32_t rlist   = (instr >> 4) & 0xF;
                uint32_t spimm   = (instr >> 2) & 0x3;
                uint32_t adj     = (rlist<=7?16u:rlist<=11?32u:rlist<=14?48u:64u) + spimm*16u;
                static const char *rn[16] = {"?","?","?","?",
                    "{ra}","{ra,s0}","{ra,s0-s1}","{ra,s0-s2}",
                    "{ra,s0-s3}","{ra,s0-s4}","{ra,s0-s5}","{ra,s0-s6}",
                    "{ra,s0-s7}","{ra,s0-s8}","{ra,s0-s9}","{ra,s0-s11}"};
                const char *rls = rlist < 16 ? rn[rlist] : "?";
                if      (ci_10_9 == 0) oss << "cm.push "    << rls << "," << "-" << adj;
                else if (ci_10_9 == 1) oss << "cm.pop "     << rls << "," << adj;
                else if (ci_10_9 == 2) oss << "cm.popretz " << rls << "," << adj;
                else                   oss << "cm.popret "  << rls << "," << adj;
                return oss.str();
            }
            return "unknown";
        }
        case 0x6: { // C.SWSP
            uint32_t uimm = ((instr >> 7) & 0x3C) | ((instr >> 1) & 0xC0);
            oss << "c.swsp " << reg_name(rs2) << "," << uimm << "(sp)";
            return oss.str();
        }
        case 0x7: { // C.SDSP (RV64 — replaces C.FSWSP)
            // offset = {instr[9:7], instr[12:10], 3'b000}
            uint32_t uimm = ((instr >> 7) & 0x38)  // o[5:3] = instr[12:10]
                          | ((instr >> 1) & 0x1C0); // o[8:6] = instr[9:7]
            oss << "c.sdsp " << reg_name(rs2) << "," << uimm << "(sp)";
            return oss.str();
        }
        default:
            return "unknown";
    }
}
