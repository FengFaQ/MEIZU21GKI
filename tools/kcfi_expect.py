#!/usr/bin/env python3
"""Extract the KCFI type hashes a vendor kernel module EXPECTS at indirect call sites.

WHY THIS EXISTS
---------------
Vendor modules resolve kernel symbols at runtime by name (mzprobe_lookup_function /
kallsyms_lookup_name) and then call them through a function pointer. Only indirect
calls are KCFI-checked, and the module hardcodes the hash it expects right at the
call site:

    ldr  w16, [x8, #-4]     ; the callee's inline type hash sits 4 bytes before entry
    movz/movk w17, #hash    ; the value the module expects
    cmp  w16, w17
    b.eq +8
    brk  #0x8228            ; CFI failure -> kernel panic   (opcode 0xd4304500)
    blr  x8

If our kernel does not carry that exact hash in front of the function, the device
panics the moment that path runs. Reading the expected value straight out of the
module is far more reliable than comparing function bodies between two images.

VALIDATION (always run the control before trusting a result)
    mz_kshrink_slabd.ko has exactly one call site and it expects 0xc3b4beac, which
    matches the "expected type: 0xc3b4beac" line in the real panic log verbatim.

NOTE: a plain 4-byte search for the hash does NOT work - the value is assembled with
movz/movk, and common values (e.g. 0xd65f03c0 "ret") occur hundreds of times by
chance. Only the decoded movz/movk constants near a brk #0x8228 are meaningful.

Usage:
    python kcfi_expect.py <module.ko> [<module.ko> ...]
"""
import struct
import sys

BRK_KCFI = 0xd4304500          # brk #0x8228
MASK_OP = 0x7F800000
OPS = {
    0x52800000: 'z32', 0x12800000: 'n32', 0x72800000: 'k32',
    0xD2800000: 'z64', 0x92800000: 'n64', 0xF2800000: 'k64',
}


def elf_sections(data):
    """[(name, type, offset, size, addr)] - just enough ELF64 for our needs."""
    e_shoff = struct.unpack_from('<Q', data, 0x28)[0]
    e_shentsize = struct.unpack_from('<H', data, 0x3A)[0]
    e_shnum = struct.unpack_from('<H', data, 0x3C)[0]
    e_shstrndx = struct.unpack_from('<H', data, 0x3E)[0]
    raw = []
    for i in range(e_shnum):
        o = e_shoff + i * e_shentsize
        name, typ, flags, addr, off, size = struct.unpack_from('<IIQQQQ', data, o)
        raw.append((name, typ, off, size, addr))
    strtab = data[raw[e_shstrndx][2]:raw[e_shstrndx][2] + raw[e_shstrndx][3]]
    out = []
    for name, typ, off, size, addr in raw:
        end = strtab.find(b'\0', name)
        out.append((strtab[name:end].decode('utf-8', 'replace'), typ, off, size, addr))
    return out


def constant_sites(text):
    """{value: [offset]} for 32-bit constants assembled by movz/movn/movk in .text."""
    out, partial = {}, {}
    for off in range(0, len(text) - 3, 4):
        w = struct.unpack_from('<I', text, off)[0]
        kind = OPS.get(w & MASK_OP)
        if kind is None:
            continue
        rd, imm16, hw = w & 0x1F, (w >> 5) & 0xFFFF, (w >> 21) & 0x3
        if kind.startswith('z'):
            val = imm16 << (hw * 16)
        elif kind.startswith('n'):
            val = (~(imm16 << (hw * 16))) & 0xFFFFFFFF
        else:                                   # movk merges into what rd holds
            val = (partial.get(rd, 0) & ~(0xFFFF << (hw * 16))) | (imm16 << (hw * 16))
        partial[rd] = val
        if kind.startswith('k'):
            out.setdefault(val & 0xFFFFFFFF, []).append(off)
    return out


def expected_hashes(path):
    """[(brk_offset, expected_hash)] for every KCFI indirect call site in the module."""
    data = open(path, 'rb').read()
    text = b''
    for name, typ, off, size, addr in elf_sections(data):
        if name == '.text':
            text = data[off:off + size]
    if not text:
        raise SystemExit('%s: no .text' % path)

    consts = constant_sites(text)
    off2val = {o: v for v, offs in consts.items() for o in offs}

    sites = []
    for i in range(0, len(text) - 3, 4):
        if struct.unpack_from('<I', text, i)[0] != BRK_KCFI:
            continue
        near = [o for o in off2val if i - 40 <= o < i]
        if near:                                # the constant is built just above the cmp
            sites.append((i, off2val[max(near)]))
    return len(text), sites


def main(paths):
    if not paths:
        raise SystemExit(__doc__)
    for path in paths:
        size, sites = expected_hashes(path)
        vals = sorted({v for _, v in sites})
        print('== %s' % path)
        print('   .text=%d B   KCFI call sites=%d   distinct expected hashes=%d'
              % (size, len(sites), len(vals)))
        for v in vals:
            where = ', '.join('0x%x' % o for o, h in sites if h == v)
            print('     0x%08x   @ %s' % (v, where))
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
