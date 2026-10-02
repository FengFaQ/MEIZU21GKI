#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""判断某个未定义符号在模块里是"函数调用"还是"数据引用"。

对每个模块读 SHT_RELA 段, 找到重定位项指向的目标符号, 按重定位类型分类:
  R_AARCH64_CALL26(283) / JUMP26(282)      -> 函数
  R_AARCH64_ABS64(257) / ABS32(258) / ...  -> 数据(也可能是函数指针取地址)
  ADR_PREL_* / ADD_ABS_LO12_NC             -> 取地址
这决定补符号时应该定义成函数还是变量。

用法: python tools/symbol_ref_kind.py <模块目录> <符号名...>
"""
import os
import struct
import sys
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from extract_module_kmi import elf_sections, iter_kos                     # noqa: E402

SHT_RELA = 4
RELOC = {
    257: "ABS64(数据)", 258: "ABS32(数据)", 259: "ABS16", 260: "PREL64",
    261: "PREL32", 262: "PREL16", 274: "ADR_PREL_PG_HI21(取地址)",
    275: "ADR_PREL_LO21(取地址)", 276: "ADR_PREL_PG_HI21_NC", 277: "ADD_ABS_LO12_NC",
    278: "LDST8_ABS_LO12_NC", 282: "JUMP26(函数)", 283: "CALL26(函数)",
    284: "LDST16_ABS_LO12_NC", 285: "LDST32_ABS_LO12_NC",
    286: "LDST64_ABS_LO12_NC", 287: "LDST128_ABS_LO12_NC",
    311: "TLSDESC_CALL", 312: "TLSDESC", 313: "TLSDESC_ADR_PAGE21",
}


def symtab(data, secs):
    """返回 symtab 索引 -> 名字。"""
    names = {}
    for s in secs:
        if s["typ"] != 2:                       # SHT_SYMTAB
            continue
        strtab = secs[s["link"]]
        entsize = s["entsize"] or 24
        for i in range(s["size"] // entsize):
            o = s["offset"] + i * entsize
            (st_name,) = struct.unpack_from("<I", data, o)
            if st_name == 0:
                continue
            end = data.index(b"\x00", strtab["offset"] + st_name)
            names[i] = data[strtab["offset"] + st_name:end].decode("utf-8", "replace")
        break
    return names


def main():
    if len(sys.argv) < 3:
        print(__doc__)
        return 2
    target, syms = sys.argv[1], set(sys.argv[2:])
    kinds = defaultdict(lambda: defaultdict(list))
    for ko in iter_kos([target]):
        data = open(ko, "rb").read()
        if data[:4] != b"\x7fELF":
            continue
        secs = elf_sections(data)
        names = symtab(data, secs)
        mod = os.path.basename(ko)
        for s in secs:
            if s["typ"] != SHT_RELA:
                continue
            entsize = s["entsize"] or 24
            for i in range(s["size"] // entsize):
                o = s["offset"] + i * entsize
                (r_off, r_info, r_addend) = struct.unpack_from("<QQq", data, o)
                r_sym = r_info >> 32
                r_type = r_info & 0xFFFFFFFF
                nm = names.get(r_sym)
                if nm not in syms:
                    continue
                kinds[nm][RELOC.get(r_type, "类型%d" % r_type)].append(mod)
    for nm in sorted(kinds):
        print("== %s" % nm)
        for k, mods in sorted(kinds[nm].items(), key=lambda x: -len(x[1])):
            uniq = sorted(set(mods))
            print("    %-34s %d 次, 模块: %s" % (k, len(mods), ", ".join(uniq[:8])))
    if not kinds:
        print("(未找到这些符号的重定位 —— 检查模块目录)")


if __name__ == "__main__":
    main()
