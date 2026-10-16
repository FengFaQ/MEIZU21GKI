#!/usr/bin/env python3
"""Verify that a kernel Image carries the inline KCFI type hash a vendor module expects.

The module hardcodes the expected hash at every indirect call site:
    ldr w16,[x8,#-4] ; movz/movk w17,#hash ; cmp w16,w17 ; b.eq +8 ; brk #0x8228 ; blr x8
The kernel must store that same hash in the 4 bytes immediately BEFORE the callee's
entry (CONFIG_CFI_CLANG inline type id).

This tool answers a different, stronger question than check_kcfi_typeid.py:
  "how many of the module's distinct expected hashes actually appear as a
   function-entry type id anywhere in the kernel Image?"

Method: scan the whole kernel .text for every occurrence of a KCFI call-site pattern
(brk #0x8228) - that finds the *callers*. To find *callee* entries we instead look for
each candidate hash placed immediately before a plausible function prologue
(paciasp 0xd503233f / bti c 0xd503245f) anywhere in the image.

Usage:
    python kcfi_coverage.py <kernel_Image> <hashes_file> [<kernel_Image2> <hashes2>]
"""
import struct
import sys

PROLOGUES = (0xd503233F, 0xD503245F)
# x16 = 0xd65f03c0 is "ret"; a hash equal to that is meaningless.
RET = 0xD65F03C0


def hash_entry_offsets(data, want_hash):
    """Offsets where `want_hash` appears as the 4 bytes preceding a prologue."""
    needle = struct.pack('<I', want_hash)
    hits = []
    start = 0
    while True:
        i = data.find(needle, start)
        if i == -1:
            break
        start = i + 1
        if i + 8 > len(data):
            continue
        nxt = struct.unpack_from('<I', data, i + 4)[0]
        if nxt in PROLOGUES:
            hits.append(i + 4)
    return hits


def main(argv):
    if len(argv) < 2:
        raise SystemExit(__doc__)
    img_path, hash_path = argv[0], argv[1]
    data = open(img_path, 'rb').read()
    hashes = []
    for line in open(hash_path):
        line = line.strip()
        if line:
            hashes.append(int(line, 16))

    print('kernel   : %s (%d B)' % (img_path, len(data)))
    print('expected : %d distinct KCFI hashes from %s' % (len(hashes), hash_path))
    print()

    found = 0
    missing = []
    for h in sorted(hashes):
        if h == RET:
            missing.append(h)
            continue
        hits = hash_entry_offsets(data, h)
        if hits:
            found += 1
            print('  0x%08x  FOUND  %d entry site(s)  first@0x%x' % (h, len(hits), hits[0]))
        else:
            missing.append(h)
            print('  0x%08x  *** NOT FOUND as any function-entry type id ***' % h)

    print()
    print('coverage: %d/%d hashes present in the kernel' % (found, len(hashes)))
    if missing:
        print('MISSING : %s' % ', '.join('0x%08x' % h for h in missing))
    return 0 if not missing else 1


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
