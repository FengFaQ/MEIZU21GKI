#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""B 方案: 把设备厂商模块期望的符号 CRC 对齐进内核(直接改 Image 里的 __kcrctab)。

为什么可行: 厂商模块用 __versions 里的 CRC 校验内核导出符号(module_layout 已一致,
结构体布局经 BTF 对比也一致 —— 见 tools/btf_diff.py), 差异只是"版本戳"。
把内核 __kcrctab 里的值改成模块期望值, 这些模块就能原样加载, 不用改厂商分区。

做法(避开 objcopy/工具链依赖):
  1. 用 vmlinux(ELF) 拿到 __ksymtab/__ksymtab_gpl/__ksymtab_strings/__kcrctab(-gpl)
     的地址与长度, 以及镜像基址(最低可加载段地址);
  2. 校验 Image 在 (段地址-基址) 处的内容与 vmlinux 段内容一致 —— 确认映射正确;
  3. 逐项解析 __ksymtab 表项(12 字节: value_offset/name_offset/namespace_offset),
     解析出符号名; __kcrctab 与 __ksymtab 逐项对应(链接器按符号名排序);
  4. 先与 Module.symvers 交叉验证对应关系(命中率必须很高), 再按清单写入期望 CRC;
  5. 回读 Image 验证写入生效, 并同步更新 Module.symvers 副本供后续报告使用。

用法:
  python tools/patch_kcrctab.py --image Image --vmlinux vmlinux \\
      --symvers Module.symvers --manifest device/meizu21/module_kmi_manifest.txt \\
      [--symvers-out Module.symvers.patched] [--report patch_crc_report.txt] [--dry-run]
"""
import argparse
import os
import re
import struct
import sys

SHT_SYMTAB = 2
SHF_ALLOC = 0x2


def elf_sections(data):
    (e_shoff,) = struct.unpack_from("<Q", data, 0x28)
    (e_shentsize, e_shnum, e_shstrndx) = struct.unpack_from("<HHH", data, 0x3A)
    secs = []
    for i in range(e_shnum):
        off = e_shoff + i * e_shentsize
        (name, typ, flags, addr, offset, size, link, info, align, entsize) = struct.unpack_from(
            "<IIQQQQIIQQ", data, off)
        secs.append({"name": name, "typ": typ, "flags": flags, "addr": addr,
                     "offset": offset, "size": size, "link": link, "entsize": entsize})
    shstr = secs[e_shstrndx]
    for s in secs:
        end = data.index(b"\x00", shstr["offset"] + s["name"])
        s["sname"] = data[shstr["offset"] + s["name"]:end].decode("utf-8", "replace")
    return secs


def load_symvers(path):
    out = {}
    order = []
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
            order.append((p[1], crc, p[2] if len(p) > 2 else "", p[3] if len(p) > 3 else ""))
    return out, order


def load_manifest(path):
    need = {}
    for line in open(path, "r", errors="replace"):
        m = re.match(r"^NEED (0x[0-9a-fA-F]+) (\S+)$", line.strip())
        if m:
            need[m.group(2)] = int(m.group(1), 16)
    return need


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--image", required=True)
    ap.add_argument("--vmlinux", required=True)
    ap.add_argument("--symvers", required=True)
    ap.add_argument("--manifest", required=True)
    ap.add_argument("--symvers-out", default=None)
    ap.add_argument("--report", default=None)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    lines = []

    def out(msg):
        print(msg)
        lines.append(msg)

    vml = open(args.vmlinux, "rb").read()
    img = bytearray(open(args.image, "rb").read())
    secs = {s["sname"]: s for s in elf_sections(vml)}
    wanted = ["__ksymtab", "__ksymtab_gpl", "__ksymtab_strings", "__kcrctab", "__kcrctab_gpl"]
    missing = [w for w in wanted if w not in secs]
    if missing:
        out("!! vmlinux 里缺段: %s" % ", ".join(missing))
        return 1

    # 镜像基址 = 最低的已分配段地址(objcopy -O binary 的起点)
    alloc = [s["addr"] for s in secs.values() if (s["flags"] & SHF_ALLOC) and s["size"] > 0]
    base = min(a for a in alloc if a > 0)
    out("镜像基址(vmlinux 最低已分配段) = 0x%x;  Image=%d 字节, vmlinux=%d 字节"
        % (base, len(img), len(vml)))

    def img_off(addr):
        return addr - base

    # 校验映射: __ksymtab_strings 的内容必须一致
    st = secs["__ksymtab_strings"]
    off = img_off(st["addr"])
    if off < 0 or off + st["size"] > len(img):
        out("!! 段地址-基址 超出 Image 范围, 映射不对")
        return 1
    same = img[off:off + st["size"]] == vml[st["offset"]:st["offset"] + st["size"]]
    out("映射自校验 __ksymtab_strings(%d 字节): %s" % (st["size"], "一致" if same else "不一致"))
    if not same:
        return 1

    symvers, order = load_symvers(args.symvers)
    need = load_manifest(args.manifest)
    out("Module.symvers 导出 %d 个; 清单 NEED %d 个" % (len(symvers), len(need)))

    strtab_off = img_off(st["addr"])

    def read_name(name_addr):
        o = img_off(name_addr)
        if o < 0 or o >= len(img):
            return None
        e = img.index(b"\x00", o)
        return img[o:e].decode("utf-8", "replace")

    # __ksymtab / __kcrctab 逐项对应
    plan = []          # (slot_offset, name, cur_crc, want_crc)
    stats = {"total": 0, "match": 0, "diff": 0, "unknown": 0, "notneed": 0}
    for tab, crcsec in (("__ksymtab", "__kcrctab"), ("__ksymtab_gpl", "__kcrctab_gpl")):
        t, c = secs[tab], secs[crcsec]
        ents = t["size"] // 12
        cs = c["size"] // 4
        if ents != cs:
            out("!! %s 表项 %d 与 %s 槽位 %d 不一致, 放弃" % (tab, ents, crcsec, cs))
            return 1
        for i in range(ents):
            eo = img_off(t["addr"]) + i * 12
            (vo, no, nso) = struct.unpack_from("<iii", img, eo)
            name = read_name(t["addr"] + i * 12 + 4 + no)
            co = img_off(c["addr"]) + i * 4
            (cur,) = struct.unpack_from("<I", img, co)
            stats["total"] += 1
            if name is None:
                stats["unknown"] += 1
                continue
            exp = symvers.get(name)
            if exp is None:
                stats["unknown"] += 1
            elif exp == cur:
                stats["match"] += 1
            else:
                stats["diff"] += 1
            want = need.get(name)
            if want is not None and want != cur:
                plan.append((co, name, cur, want))

    out("对应关系校验: 共 %d 项, 与 Module.symvers 一致 %d, 不一致 %d, 未知 %d"
        % (stats["total"], stats["match"], stats["diff"], stats["unknown"]))
    if stats["match"] + stats["diff"] == 0:
        out("!! 一个都没对上, 放弃(排序假设不成立)")
        return 1
    rate = stats["match"] * 100.0 / max(1, stats["match"] + stats["diff"])
    out("命中率 %.2f%%" % rate)
    if rate < 90:
        out("!! 命中率过低, 放弃")
        return 1

    out("\n需要改写的符号 %d 个:" % len(plan))
    for co, name, cur, want in plan[:40]:
        out("   %-40s 0x%08x -> 0x%08x" % (name, cur, want))
    if len(plan) > 40:
        out("   ... 另有 %d 个" % (len(plan) - 40))

    need_missing = [n for n in need if n not in symvers]
    out("\n清单里需要但内核未导出的符号 %d 个(应由 A 方案补符号解决):" % len(need_missing))
    for n in sorted(need_missing):
        out("   %s" % n)

    if args.dry_run:
        out("\n(dry-run, 未写入)")
        return 0

    for co, name, cur, want in plan:
        struct.pack_into("<I", img, co, want)

    # 回读校验
    bad = 0
    for co, name, cur, want in plan:
        (now,) = struct.unpack_from("<I", img, co)
        if now != want:
            bad += 1
    out("\n回读校验: %d/%d 写入成功%s" % (len(plan) - bad, len(plan), "" if bad == 0 else " (有失败!)"))
    if bad:
        return 1

    with open(args.image, "wb") as f:
        f.write(img)
    out("已写入 %s" % args.image)

    if args.symvers_out:
        with open(args.symvers_out, "w") as f:
            for name, crc, mod, kind in order:
                new = need.get(name, crc)
                f.write("0x%08x\t%s\t%s\t%s\t\n" % (new, name, mod, kind))
        out("已写出对齐后的 Module.symvers: %s" % args.symvers_out)

    if args.report:
        with open(args.report, "w", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
