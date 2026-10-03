#!/usr/bin/env python3
"""Compare Android boot images (header v0-v4) field by field.

Also reports where the payload really ends, whether the tail is pure zero
padding, and whether an AVB footer is present.

Usage: python bootcompare.py <a.img> [b.img ...]
"""
import hashlib
import os
import struct
import sys


def u32(d, off):
    return struct.unpack_from('<I', d, off)[0]


def parse(path):
    d = open(path, 'rb').read()
    info = {'path': path, 'size': len(d)}
    info['magic'] = d[:8]
    if d[:8] != b'ANDROID!':
        return info
    hv = u32(d, 40)
    info['header_version'] = hv
    if hv >= 3:
        info['kernel_size'] = u32(d, 8)
        info['ramdisk_size'] = u32(d, 12)
        info['os_version'] = u32(d, 16)
        info['header_size'] = u32(d, 20)
        info['cmdline'] = d[44:44 + 1536].split(b'\x00')[0].decode('ascii', 'replace')
        info['signature_size'] = u32(d, 1580) if len(d) >= 1584 else 0
        page = 4096
    else:
        info['kernel_size'] = u32(d, 8)
        info['kernel_addr'] = u32(d, 12)
        info['ramdisk_size'] = u32(d, 16)
        info['ramdisk_addr'] = u32(d, 20)
        info['second_size'] = u32(d, 24)
        info['second_addr'] = u32(d, 28)
        info['tags_addr'] = u32(d, 32)
        page = u32(d, 36)
        info['page_size'] = page
        info['dt_size'] = u32(d, 40)
        info['os_version'] = u32(d, 44)
        info['name'] = d[48:64].split(b'\x00')[0].decode('ascii', 'replace')
        info['cmdline'] = d[64:576].split(b'\x00')[0].decode('ascii', 'replace')
        info['extra_cmdline'] = d[608:1632].split(b'\x00')[0].decode('ascii', 'replace')
    info['page_size_used'] = page
    ks = info['kernel_size']
    rs = info['ramdisk_size']
    info['kernel_offset'] = page
    info['ramdisk_offset'] = page + ((ks + page - 1) // page) * page
    info['signature_offset'] = info['ramdisk_offset'] + ((rs + page - 1) // page) * page
    sec = info.get('second_size', 0) or 0
    dt = info.get('dt_size', 0) or 0
    info['data_end'] = (info['signature_offset'] + info.get('signature_size', 0)
                        + ((sec + page - 1) // page) * page + ((dt + page - 1) // page) * page)
    tail = d[info['data_end']:]
    info['tail_len'] = len(tail)
    info['tail_all_zero'] = (tail.count(0) == len(tail)) if tail else True
    info['tail_nonzero'] = len(tail) - tail.count(0)
    info['avb_magic_off'] = d.rfind(b'AVBf')
    info['avb_footer'] = info['avb_magic_off'] >= len(d) - 4096
    info['kernel_md5'] = hashlib.md5(
        d[info['kernel_offset']:info['kernel_offset'] + ks]).hexdigest().upper()
    return info


def show(i):
    print('  file            : %s' % i['path'])
    print('  size            : %d bytes (%.3f MiB)' % (i['size'], i['size'] / 1048576.0))
    print('  magic           : %r' % i.get('magic'))
    if i.get('magic') != b'ANDROID!':
        print('  (not an Android boot image)')
        return
    print('  header_version  : %d' % i['header_version'])
    print('  header_size     : %s' % i.get('header_size', '-'))
    print('  page_size       : %s' % i.get('page_size', i.get('page_size_used')))
    print('  kernel_size     : %d (%.3f MiB)' % (i['kernel_size'], i['kernel_size'] / 1048576.0))
    print('  ramdisk_size    : %d' % i['ramdisk_size'])
    if 'second_size' in i:
        print('  second_size     : %d' % i['second_size'])
        print('  dt_size         : %d' % i.get('dt_size', 0))
        print('  kernel_addr     : 0x%x' % i['kernel_addr'])
        print('  ramdisk_addr    : 0x%x' % i['ramdisk_addr'])
        print('  tags_addr       : 0x%x' % i['tags_addr'])
        print('  name            : %r' % i.get('name'))
    if i['header_version'] >= 3:
        print('  signature_size  : %d' % i.get('signature_size', 0))
    print('  os_version      : 0x%08x' % i['os_version'])
    print('  cmdline         : %r' % i.get('cmdline'))
    if 'extra_cmdline' in i:
        print('  extra_cmdline   : %r' % i['extra_cmdline'])
    print('  kernel  @0x%-8x md5=%s' % (i['kernel_offset'], i['kernel_md5']))
    print('  ramdisk @0x%-8x' % i['ramdisk_offset'])
    print('  payload ends    : 0x%x (%d bytes)' % (i['data_end'], i['data_end']))
    print('  padding tail    : %d bytes, all-zero=%s (nonzero=%d)'
          % (i['tail_len'], i['tail_all_zero'], i['tail_nonzero']))
    if i['avb_magic_off'] >= 0:
        print('  AVB "AVBf" at   : 0x%x (footer=%s)'
              % (i['avb_magic_off'], i['avb_footer']))
    else:
        print('  AVB footer      : none')
    print('  partition fill  : %.1f%% (payload %d of %d)'
          % (100.0 * i['data_end'] / i['size'], i['data_end'], i['size']))


for p in sys.argv[1:]:
    if not os.path.isfile(p):
        print('  MISSING: %s' % p)
        continue
    show(parse(p))
    print('')
