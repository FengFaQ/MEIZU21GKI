#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""用"内核导出 + 模块互供 + 首阶段加载"三方关系, 重新判定设备模块真正缺什么。

之前 module_compat.txt / check_module_kmi.py 把"由其它模块提供的符号"误判成
"内核缺失/CRC 不一致", 导致 17 MISSING + 74 不一致的假象。这里按真实供给关系分类:

  KERNEL_OK     : 我们内核导出且 CRC 一致            -> 没问题
  KERNEL_CRC    : 我们内核导出但 CRC 不一致          -> 真问题(需对齐)
  MODULE_DEF    : 由某个 .ko 提供(模块互供)          -> CRC 来自该模块, 与内核无关
  MISSING       : 我们内核没有、模块也没提供         -> 真问题(需补符号)
"""
import os
import re
import sys
from collections import defaultdict

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
W = os.path.join(ROOT, "work")


def load_symvers(path):
    """Module.symvers: 0x<crc>\t<sym>\t<module>\t<ns>\t<type>"""
    out = {}
    if not os.path.exists(path):
        return out
    with open(path, "r", errors="replace") as f:
        for line in f:
            p = line.rstrip("\n").split("\t")
            if len(p) < 3:
                continue
            try:
                crc = int(p[0], 16)
            except ValueError:
                continue
            out[p[1]] = crc
    return out


def load_manifest(path):
    """NEED 0x<crc> <sym> / DEF 0x<crc> <sym>"""
    need = defaultdict(dict)   # sym -> {crc: [..]}  (不同模块可能期望不同)
    need_by_mod = defaultdict(list)
    deff = defaultdict(set)
    cur_mod = None
    with open(path, "r", errors="replace") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            if line.startswith("MODULE "):
                cur_mod = line.split(None, 1)[1]
                continue
            m = re.match(r"^(NEED|DEF) (0x[0-9a-fA-F]+) (\S+)$", line)
            if not m:
                continue
            kind, crc, sym = m.group(1), int(m.group(2), 16), m.group(3)
            if kind == "NEED":
                need[sym].setdefault(crc, []).append(cur_mod)
                need_by_mod[cur_mod].append(sym)
            else:
                deff[sym].add(cur_mod)
    return need, need_by_mod, deff


def load_first_stage(root):
    """从 vendor_ramdisk 里取 modules.load / modules.load.recovery 的模块名。"""
    names = []
    for base, _, files in os.walk(root):
        for fn in files:
            if fn.startswith("modules.load"):
                try:
                    with open(os.path.join(base, fn), errors="replace") as f:
                        for line in f:
                            line = line.strip()
                            if line and not line.startswith("#"):
                                names.append(os.path.basename(line))
                except OSError:
                    pass
    return set(names)


def main():
    symvers = load_symvers(os.path.join(W, "dist8", "Module.symvers"))
    need, need_by_mod, deff = load_manifest(os.path.join(ROOT, "MEIZU21GKI", "device", "meizu21", "module_kmi_manifest.txt"))
    first = load_first_stage(os.path.join(W, "vendor_ramdisk_root"))
    print("我们内核导出符号 %d 个; manifest NEED %d 个; DEF %d 个; 首阶段模块 %d 个"
          % (len(symvers), len(need), len(deff), len(first)))

    ok = crc_bad = module_def = missing = 0
    bad_list = []
    miss_list = []
    for sym, crcs in sorted(need.items()):
        consumers = [m for v in crcs.values() for m in v if m]
        fs = [m for m in consumers if m and m in first]
        if sym in symvers:
            if symvers[sym] in crcs:
                ok += 1
            else:
                crc_bad += 1
                bad_list.append((sym, sorted(crcs), symvers[sym], fs, consumers[:3]))
        elif sym in deff:
            module_def += 1
        else:
            missing += 1
            miss_list.append((sym, sorted(crcs), fs, consumers[:3]))

    print("\n== 分类结果 ==")
    print("  内核导出且 CRC 一致 : %d" % ok)
    print("  内核导出但 CRC 不一致: %d" % crc_bad)
    print("  由模块互供(与内核无关): %d" % module_def)
    print("  两边都没有(真缺符号)  : %d" % missing)

    print("\n== 真·CRC 不一致 (内核侧) ==")
    for sym, crcs, ours, fs, cons in bad_list:
        tag = "  [首阶段!]" if fs else ""
        print("  %-38s 期望 %s 我们 0x%08x%s  用于: %s" %
              (sym, ",".join("0x%08x" % c for c in crcs), ours, tag, ",".join(cons)))

    print("\n== 真·缺符号 (需补) ==")
    for sym, crcs, fs, cons in miss_list:
        tag = "  [首阶段!]" if fs else ""
        print("  %-38s 期望 %s%s  用于: %s" %
              (sym, ",".join("0x%08x" % c for c in crcs), tag, ",".join(cons)))

    # 首阶段模块的完整需求清单里, 有多少完全满足
    fs_syms = set()
    for sym, crcs in need.items():
        for m in [x for v in crcs.values() for x in v]:
            if m in first:
                fs_syms.add(sym)
    fs_bad = [s for s in fs_syms if (s in symvers and symvers[s] not in need[s]) or (s not in symvers and s not in deff)]
    print("\n首阶段模块共需要 %d 个符号, 其中有问题 %d 个" % (len(fs_syms), len(fs_bad)))
    for s in sorted(fs_bad):
        print("   -", s)


if __name__ == "__main__":
    main()
