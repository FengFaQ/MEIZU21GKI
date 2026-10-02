#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""逐个模块判定: 我们的内核能否加载它, 并区分"内核 CRC 不一致 / 缺符号 / 模块互供"。

关键用途: 把 74 个 CRC 不一致按"模块 vermagic"分组 —— 如果只有旧 vermagic
(6.1.25 无 -android14-11) 的模块受影响, 说明它们是旧固件残留, 与本次卡logo无关。

用法:
  python tools/per_module_compat.py [模块目录...]    # 默认用 work 下的三处解包目录
"""
import os
import struct
import sys
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from extract_module_kmi import elf_sections, read_versions, read_defined, read_vermagic, iter_kos  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
W = os.path.join(ROOT, "work")


def load_symvers(path):
    out = {}
    with open(path, "r", errors="replace") as f:
        for line in f:
            p = line.rstrip("\n").split("\t")
            if len(p) >= 3:
                try:
                    out[p[1]] = int(p[0], 16)
                except ValueError:
                    pass
    return out


def load_loadlist(root):
    stages = {}
    for base, _, files in os.walk(root):
        for fn in files:
            if fn.startswith("modules.load"):
                mods = []
                with open(os.path.join(base, fn), errors="replace") as f:
                    for line in f:
                        line = line.strip()
                        if line and not line.startswith("#"):
                            mods.append(os.path.basename(line))
                stages[fn] = set(mods)
    return stages


def main():
    sources = sys.argv[1:] or [os.path.join(W, "vendor_ramdisk_root"),
                               os.path.join(W, "sd_out"), os.path.join(W, "vd_out")]
    sources = [s for s in sources if os.path.exists(s)]
    symvers = load_symvers(os.path.join(W, "dist8", "Module.symvers"))
    stages = load_loadlist(os.path.join(W, "vendor_ramdisk_root"))
    first_only = stages.get("modules.load", set())
    print("内核导出 %d; 模块目录 %s; 首阶段 modules.load %d 个模块"
          % (len(symvers), sources, len(first_only)))

    info = {}
    provided_by = defaultdict(set)
    kos = list(iter_kos(sources))
    for ko in kos:
        name = os.path.basename(ko)
        try:
            data = open(ko, "rb").read()
            secs = elf_sections(data)
            info[name] = {"need": read_versions(data, secs), "vm": read_vermagic(data),
                          "def": read_defined(data, secs)}
        except Exception as exc:                       # noqa: BLE001
            print("  跳过 %s: %s" % (name, exc))
        else:
            for s in info[name]["def"]:
                provided_by[s].add(name)

    def classify(name):
        bad_crc, missing, mod_only, ok = [], [], [], 0
        for sym, crc in info[name]["need"].items():
            if sym in symvers:
                if symvers[sym] == crc:
                    ok += 1
                else:
                    bad_crc.append(sym)
            elif sym in provided_by and provided_by[sym] - {name}:
                mod_only.append(sym)
            else:
                missing.append(sym)
        return ok, bad_crc, missing, mod_only

    by_vm = defaultdict(lambda: [0, 0, 0])             # vermagic -> [模块数, 有CRC问题, 有缺失]
    failing = []
    for name in sorted(info):
        ok, bad, miss, mod_only = classify(name)
        vm = info[name]["vm"]
        by_vm[vm][0] += 1
        if bad:
            by_vm[vm][1] += 1
        if miss:
            by_vm[vm][2] += 1
        if bad or miss:
            failing.append((name, vm, bad, miss, name in first_only))

    print("\n== 按 vermagic 分组 (模块数 / 有CRC不一致 / 有缺符号) ==")
    for vm, (n, b, m) in sorted(by_vm.items(), key=lambda x: -x[1][0]):
        print("  %-52s %4d / %4d / %4d" % (vm or "(无)", n, b, m))

    print("\n== 有问题的模块 %d 个 (★=首阶段 modules.load) ==" % len(failing))
    for name, vm, bad, miss, fs in failing[:60]:
        print("  %s %-34s vm=%s" % ("★" if fs else " ", name, vm or "(无)"))
        if bad:
            print("      CRC不一致 %d: %s" % (len(bad), ", ".join(bad[:6])))
        if miss:
            print("      缺符号   %d: %s" % (len(miss), ", ".join(miss[:6])))

    fs_fail = [f for f in failing if f[4]]
    print("\n★ 首阶段模块里有问题的: %d 个" % len(fs_fail))
    for name, vm, bad, miss, _ in fs_fail:
        print("   %-34s CRC不一致=%d 缺符号=%d  %s" % (name, len(bad), len(miss), ",".join((bad + miss)[:4])))

    # 汇总 74/17 到底影响哪些模块
    all_bad = set()
    all_miss = set()
    for name in info:
        _ok, bad, miss, _mo = classify(name)
        all_bad.update(bad)
        all_miss.update(miss)
    print("\n合计受影响符号: CRC不一致 %d 个 / 缺符号 %d 个" % (len(all_bad), len(all_miss)))
    print("缺符号清单: %s" % ", ".join(sorted(all_miss)))

    # 反向索引: 每个问题符号被哪些模块需要(是否首阶段)
    consumers = defaultdict(list)
    for name, d in info.items():
        for sym in d["need"]:
            consumers[sym].append(name)
    print("\n== 问题符号 → 使用它的模块 (★=首阶段) ==")
    for sym in sorted(all_miss) + sorted(all_bad):
        kind = "缺符号" if sym in all_miss else "CRC  "
        cs = sorted(consumers.get(sym, []))
        star = [c for c in cs if c in first_only]
        print("  [%s] %-42s 模块 %d 个%s" %
              (kind, sym, len(cs), ("  首阶段: " + ", ".join(star)) if star else ""))
        if not star and cs:
            print("         (非首阶段) %s" % ", ".join(cs[:6]))


if __name__ == "__main__":
    main()
