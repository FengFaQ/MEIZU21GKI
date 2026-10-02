#!/usr/bin/env python3
"""检查 devices 的 modules.load 列表里, 哪些模块会因"内核缺符号"而加载失败。

第一阶段的 init 只要有一个 modules.load 条目加载失败, 可能直接 FATAL → 重启,
现象正是"卡第一屏 2~3 秒后自动重启"。
"""
import os
import re
import struct

ROOT = r"C:\work\pt\meizu21-gki"


def elf(data):
    (e_shoff,) = struct.unpack_from("<Q", data, 0x28)
    (e_shentsize, e_shnum, e_shstrndx) = struct.unpack_from("<HHH", data, 0x3A)
    secs = []
    for i in range(e_shnum):
        o = e_shoff + i * e_shentsize
        nm, typ, fl, ad, off, sz, lk, inf, al, es = struct.unpack_from("<IIQQQQIIQQ", data, o)
        secs.append(dict(nm=nm, typ=typ, off=off, sz=sz, lk=lk, es=es))
    sh = secs[e_shstrndx]
    for s in secs:
        e = data.index(b"\x00", sh["off"] + s["nm"])
        s["name"] = data[sh["off"] + s["nm"]:e].decode()
    return secs


def versions(data, secs):
    out = {}
    for s in secs:
        if s["name"] == "__versions":
            for i in range(s["sz"] // 64):
                o = s["off"] + i * 64
                crc, = struct.unpack_from("<Q", data, o)
                nm = data[o + 8:o + 64].split(b"\x00")[0].decode("utf-8", "replace")
                if nm:
                    out[nm] = crc
    return out


def defined(data, secs):
    out = set()
    for s in secs:
        if s["typ"] != 2:
            continue
        st = secs[s["lk"]]
        es = s["es"] or 24
        for i in range(s["sz"] // es):
            o = s["off"] + i * es
            nm, info, other, shndx = struct.unpack_from("<IBBH", data, o)
            if shndx == 0 or nm == 0 or (info >> 4) not in (1, 2):
                continue
            e = data.index(b"\x00", st["off"] + nm)
            out.add(data[st["off"] + nm:e].decode("utf-8", "replace"))
    return out


mods = {}
for base in (r"work\vendor_ramdisk_root\lib\modules",
             r"work\vd_out\vendor_dlkm_a\lib\modules",
             r"work\sd_out\system_dlkm_a"):
    for root, _dirs, files in os.walk(os.path.join(ROOT, base)):
        for f in files:
            if f.endswith(".ko"):
                p = os.path.join(root, f)
                try:
                    d = open(p, "rb").read()
                    s = elf(d)
                    mods[f] = (versions(d, s), defined(d, s), p)
                except Exception:                              # noqa: BLE001
                    pass

allprov = set()
for _n, d, _p in mods.values():
    allprov |= d
print(f"模块总数 {len(mods)}, 模块间提供符号 {len(allprov)}")

load_lists = []
for root, _dirs, files in os.walk(os.path.join(ROOT, "work")):
    for f in files:
        if f.startswith("modules.load"):
            load_lists.append(os.path.join(root, f))

for p in sorted(load_lists):
    entries = [l.strip() for l in open(p, encoding="utf-8", errors="replace")
               if l.strip() and not l.startswith("#")]
    rel = os.path.relpath(p, ROOT)
    print(f"\n===== {rel}: {len(entries)} 项 =====")
    suspicious = []
    missing_local = []
    for m in entries:
        if m not in mods:
            missing_local.append(m)
            continue
        need = mods[m][0]
        ext = [s for s in need if s not in allprov]
        odd = [s for s in ext if re.match(r"^(mz_|mzc_|meizu|flyme)", s)]
        if odd:
            suspicious.append((m, odd))
    if missing_local:
        print(f"  列表里有、本地没抓到 .ko 的: {missing_local[:8]}")
    print("  依赖『内核提供且名字像魅族私有』符号的模块:")
    if suspicious:
        for m, odd in suspicious:
            print(f"    {m}: {odd[:8]}")
    else:
        print("    (无)")
