#!/usr/bin/env python3
"""Minimal AArch64 disassembler for the subset of instructions we need.

Purpose: inspect what a vendor module's function does when the kernel has no
objdump available. We only decode the common integer/load-store/branch forms.
"""
import struct
import sys

REGS = ['x%d' % i for i in range(31)] + ['sp']
WREGS = ['w%d' % i for i in range(31)] + ['wzr']


def sx(v, bits):
    if v & (1 << (bits - 1)):
        v -= (1 << bits)
    return v


def dis(w, addr):
    """Return a mnemonic string for one 32-bit instruction."""
    # NOP / hint
    if w == 0xD503201F:
        return 'nop'
    if w == 0xD503233F:
        return 'paciasp'
    if w == 0xD50323BF:
        return 'autiasp'
    if w == 0xD65F03C0:
        return 'ret'
    if w & 0xFFFFFC1F == 0xD65F0000:
        return 'ret %s' % REGS[(w >> 5) & 31]
    if w == 0xD4304500:
        return 'brk #0x8228   <-- KCFI trap'
    if w & 0xFFE0001F == 0xD4200000:
        return 'brk #%d' % ((w >> 5) & 0xFFFF)

    # B / BL
    if w & 0xFC000000 == 0x14000000:
        off = sx(w & 0x03FFFFFF, 26) * 4
        return '%s 0x%x' % ('b' if not (w >> 31) else 'bl', addr + off)
    if w & 0xFF000010 == 0x54000000:
        off = sx((w >> 5) & 0x7FFFF, 19) * 4
        cond = ['eq', 'ne', 'cs', 'cc', 'mi', 'pl', 'vs', 'vc',
                'hi', 'ls', 'ge', 'lt', 'gt', 'le', 'al', 'nv'][w & 0xF]
        return 'b.%s 0x%x' % (cond, addr + off)
    if w & 0x7E000000 == 0x34000000:
        off = sx((w >> 5) & 0x7FFFF, 19) * 4
        rt = WREGS[w & 31] if (w >> 31) else REGS[w & 31]
        return '%s %s, 0x%x' % ('cbnz' if (w >> 24) & 1 else 'cbz', rt, addr + off)
    if w & 0x7E000000 == 0x36000000:
        off = sx((w >> 5) & 0x7FFFF, 19) * 4
        rt = WREGS[w & 31] if (w >> 31) else REGS[w & 31]
        return '%s %s, #%d, 0x%x' % ('tbnz' if (w >> 24) & 1 else 'tbz', rt, (w >> 19) & 31, addr + off)
    if w & 0xFFFFFC1F == 0xD63F0000:
        return 'blr %s' % REGS[(w >> 5) & 31]

    # MOVZ / MOVN / MOVK
    ops = {0x52800000: 'movz', 0x12800000: 'movn', 0x72800000: 'movk'}
    for base, name in ops.items():
        if w & 0x7F800000 == base:
            rd = WREGS[(w >> 0) & 31] if not (base & 0x80000000) else REGS[(w >> 0) & 31]
            imm = (w >> 5) & 0xFFFF
            hw = (w >> 21) & 3
            s = '#0x%x' % (imm << (hw * 16))
            if hw:
                s += ', lsl #%d' % (hw * 16)
            return '%s %s, %s' % (name, rd, s)
    for base, name in {0xD2800000: 'movz', 0x92800000: 'movn', 0xF2800000: 'movk'}.items():
        if w & 0x7F800000 == base:
            rd = REGS[(w >> 0) & 31]
            imm = (w >> 5) & 0xFFFF
            hw = (w >> 21) & 3
            s = '#0x%x' % (imm << (hw * 16))
            if hw:
                s += ', lsl #%d' % (hw * 16)
            return '%s %s, %s' % (name, rd, s)

    # ORR (incl. MOV reg)
    if w & 0x7F200000 == 0x2A000000:
        rd, rn, rm = w & 31, (w >> 5) & 31, (w >> 16) & 31
        if rn == 31:
            return 'mov %s, %s' % (WREGS[rd], WREGS[rm])
        return 'orr %s, %s, %s' % (WREGS[rd], WREGS[rn], WREGS[rm])
    if w & 0x7F200000 == 0xAA000000:
        rd, rn, rm = w & 31, (w >> 5) & 31, (w >> 16) & 31
        if rn == 31:
            return 'mov %s, %s' % (REGS[rd], REGS[rm])
        return 'orr %s, %s, %s' % (REGS[rd], REGS[rn], REGS[rm])

    # ADD/SUB imm
    if w & 0x7F000000 in (0x11000000, 0x51000000):
        sub = (w >> 30) & 1
        rd, rn = w & 31, (w >> 5) & 31
        imm = (w >> 10) & 0xFFF
        sf = (w >> 31) & 1
        R = REGS if sf else WREGS
        return '%s %s, %s, #0x%x' % ('sub' if sub else 'add', R[rd], R[rn], imm)

    # LDR/STR (unsigned offset)
    if w & 0x3B000000 == 0x39000000:
        size = (w >> 30) & 3
        opc = (w >> 22) & 3
        rt = w & 31
        rn = (w >> 5) & 31
        imm = ((w >> 10) & 0xFFF) << size
        load = (opc >> 1) & 1
        nm = {0: 'ldrb' if load else 'strb', 1: 'ldrh' if load else 'strh',
              2: 'ldr' if load else 'str', 3: 'ldr' if load else 'str'}[size]
        reg = REGS[rt]
        if size == 2 and not (w >> 31):
            reg = WREGS[rt]
        return '%s %s, [%s, #0x%x]' % (nm, reg, REGS[rn] if rn != 31 else 'sp', imm)
    if w & 0x3B200C00 == 0x38000000:
        # unscaled / pre / post index
        size = (w >> 30) & 3
        opc = (w >> 22) & 3
        rt = w & 31
        rn = (w >> 5) & 31
        imm = sx((w >> 12) & 0x1FF, 9)
        mode = (w >> 10) & 3
        load = (opc >> 1) & 1
        nm = {0: 'ldurb' if load else 'sturb', 1: 'ldurh' if load else 'sturh',
              2: 'ldur' if load else 'stur', 3: 'ldur' if load else 'stur'}[size]
        tail = {1: ']!', 3: '], #%d' % imm}.get(mode, ']')
        if mode == 1:
            return '%s %s, [%s, #%d]!' % (nm, REGS[rt], REGS[rn], imm)
        if mode == 3:
            return '%s %s, [%s], #%d' % (nm, REGS[rt], REGS[rn], imm)
        return '%s %s, [%s, #%d]' % (nm, REGS[rt], REGS[rn], imm)

    # CMP (SUBS imm / reg)
    if w & 0x7F000000 == 0x71000000:
        rd = w & 31
        rn = (w >> 5) & 31
        imm = (w >> 10) & 0xFFF
        sf = (w >> 31) & 1
        if rd == 31:
            R = REGS if sf else WREGS
            return 'cmp %s, #0x%x' % (R[rn], imm)
    if w & 0x7F200000 == 0x6B000000:
        rd, rn, rm = w & 31, (w >> 5) & 31, (w >> 16) & 31
        sf = (w >> 31) & 1
        if rd == 31:
            R = REGS if sf else WREGS
            return 'cmp %s, %s' % (R[rn], R[rm])

    # STP/LDP
    if w & 0x3A000000 == 0x28000000:
        opc = (w >> 30) & 3
        rt = w & 31
        rt2 = (w >> 10) & 31
        rn = (w >> 5) & 31
        imm = sx((w >> 15) & 0x7F, 7) * 8
        load = (w >> 22) & 1
        nm = 'ldp' if load else 'stp'
        return '%s %s, %s, [%s, #%d]' % (nm, REGS[rt], REGS[rt2], REGS[rn], imm)
    if w & 0xFFC00000 == 0xA9000000:
        rt, rt2, rn = w & 31, (w >> 10) & 31, (w >> 5) & 31
        imm = sx((w >> 15) & 0x7F, 7) * 8
        return 'stp %s, %s, [%s, #%d]' % (REGS[rt], REGS[rt2], REGS[rn], imm)
    if w & 0xFFC00000 == 0xA9400000:
        rt, rt2, rn = w & 31, (w >> 10) & 31, (w >> 5) & 31
        imm = sx((w >> 15) & 0x7F, 7) * 8
        return 'ldp %s, %s, [%s, #%d]' % (REGS[rt], REGS[rt2], REGS[rn], imm)

    # ADRP / ADR
    if w & 0x9F000000 == 0x90000000:
        immlo = (w >> 29) & 3
        immhi = (w >> 5) & 0x7FFFF
        imm = sx((immhi << 2) | immlo, 21) << 12
        return 'adrp %s, 0x%x' % (REGS[w & 31], (addr & ~0xFFF) + imm)
    if w & 0x9F000000 == 0x10000000:
        immlo = (w >> 29) & 3
        immhi = (w >> 5) & 0x7FFFF
        imm = sx((immhi << 2) | immlo, 21)
        return 'adr %s, 0x%x' % (REGS[w & 31], addr + imm)

    # MADD / MSUB
    if w & 0x7FE08000 == 0x1B000000:
        rd, rn, rm, ra = w & 31, (w >> 5) & 31, (w >> 16) & 31, (w >> 10) & 31
        sf = (w >> 31) & 1
        R = REGS if sf else WREGS
        return 'madd %s, %s, %s, %s' % (R[rd], R[rn], R[rm], R[ra])

    # LDXR/STXR/atomics - just name them
    for mask, name in ((0xFFE08000, 'ldxr'), (0xFFE08000, 'stxr')):
        pass

    return '??? (0x%08x)' % w


def main(argv):
    if len(argv) < 3:
        raise SystemExit('usage: a64dis.py <module.ko> <hex_offset> <hex_len>')
    path = argv[0]
    start = int(argv[1], 16)
    length = int(argv[2], 16)
    d = open(path, 'rb').read()
    for i in range(0, length, 4):
        off = start + i
        w = struct.unpack_from('<I', d, off)[0]
        print('  0x%06x:  %08x  %s' % (off, w, dis(w, off)))
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
