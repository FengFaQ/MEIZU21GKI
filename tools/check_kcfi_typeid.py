#!/usr/bin/env python3
"""Check the KCFI inline type hash that precedes a kernel function in an Image.

Why not use `nm vmlinux | grep __kcfi_typeid_`:
    the inline 4-byte hash in front of a function and the named
    __kcfi_typeid_<name> symbol are two different things. The named symbol is
    only emitted when the type id has to be referenced from another
    translation unit. Proof: kfree HAS an inline hash (0x9390bcfa, identical in
    stock and in our build) but there is no __kcfi_typeid_kfree symbol at all.
    So the only trustworthy test is to read the bytes in the Image itself.

Layout facts used here (all measured, not assumed):
    * an arm64 Image maps 1:1 onto runtime addresses starting at _text, so a
      function's (addr - _text) is also its file offset in the Image
    * with CONFIG_CFI_CLANG the 4 bytes right before the function are its type id

Usage:
    python check_kcfi_typeid.py <Image> <hex_offset> [expected_hex]
    python check_kcfi_typeid.py <Image> --nm <vmlinux> [expected_hex]
"""
import struct
import subprocess
import sys

PROLOGUES = {
    0xd503233f: 'paciasp',
    0xd503245f: 'bti c',
}


def read_typeid(path, off):
    with open(path, 'rb') as fh:
        fh.seek(off - 4)
        tid = struct.unpack('<I', fh.read(4))[0]
        ins = struct.unpack('<4I', fh.read(16))
    return tid, ins


def offset_from_nm(image, vmlinux, symbol):
    """offset = sym_addr - _text, taken from nm output."""
    addrs = {}
    out = subprocess.run(['nm', vmlinux], capture_output=True, text=True).stdout
    for line in out.splitlines():
        parts = line.split()
        if len(parts) == 3 and parts[2] in ('_text', symbol):
            try:
                addrs[parts[2]] = int(parts[0], 16)
            except ValueError:
                pass
    if '_text' not in addrs or symbol not in addrs:
        sys.exit('cannot resolve _text/%s from %s' % (symbol, vmlinux))
    return addrs[symbol] - addrs['_text']


def main():
    args = sys.argv[1:]
    if not args:
        sys.exit(__doc__)
    image = args[0]
    expected = None
    if '--nm' in args:
        i = args.index('--nm')
        vmlinux, symbol = args[i + 1], args[i + 2]
        off = offset_from_nm(image, vmlinux, symbol)
        rest = args[1:i]
        if rest:
            expected = int(rest[0], 16)
        if len(args) > i + 3:
            expected = int(args[i + 3], 16)
    else:
        off = int(args[1], 16)
        if len(args) > 2:
            expected = int(args[2], 16)

    tid, ins = read_typeid(image, off)
    tag = PROLOGUES.get(ins[0])
    print('image          : %s' % image)
    print('offset         : 0x%x' % off)
    print('typeid (4B bef): 0x%08x' % tid)
    print('first insns    : %s' % ' '.join('%08x' % x for x in ins))
    if tag:
        print('prologue       : %s  <- looks like a real function entry' % tag)
    else:
        print('prologue       : UNRECOGNISED (0x%08x) - offset may be wrong,'
              ' or the 4 bytes are the tail of the previous function' % ins[0])
    if tid == 0xd65f03c0 or ins[0] == 0xd65f03c0:
        print('NOTE           : 0xd65f03c0 is "ret", i.e. the end of the'
              ' previous function -> this function has NO inline type id')
    if expected is not None:
        ok = tid == expected
        print('expected       : 0x%08x -> %s' % (expected, 'MATCH' if ok else 'MISMATCH'))
        sys.exit(0 if ok else 1)
    return 0


if __name__ == '__main__':
    sys.exit(main() or 0)
