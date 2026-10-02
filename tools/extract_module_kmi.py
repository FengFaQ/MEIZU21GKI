#!/usr/bin/env python3
"""从设备模块(.ko)抽取 KMI 依赖清单, 用于"不刷机就验证内核能否加载厂商模块"。

原理:
  * CONFIG_MODVERSIONS=y 的模块带 __versions 段, 每项 64 字节:
      struct modversion_info { unsigned long crc; char name[56]; };
    内核加载模块时会逐个比对符号 CRC(same_magic 会跳过版本串, 因为 CRC 才是真校验),
    CRC 不一致 → "disagrees about version of symbol X" → 模块拒载 → 驱动缺失 → 卡第一屏后重启。
  * 另外收集模块自己定义(导出)的符号, 避免把"模块间互相提供"的符号误判成缺失。

用法:
  python tools/extract_module_kmi.py <输出清单> <目录或 .ko 路径>...
"""
import os
import struct
import sys

MODVERSION_ENTRY = 64          # 8 字节 crc + 56 字节 name
SHT_SYMTAB = 2
SHN_UNDEF = 0


def elf_sections(data):
    (e_shoff,) = struct.unpack_from("<Q", data, 0x28)
    (e_shentsize, e_shnum, e_shstrndx) = struct.unpack_from("<HHH", data, 0x3A)
    secs = []
    for i in range(e_shnum):
        off = e_shoff + i * e_shentsize
        (name, typ, flags, addr, offset, size, link, info, align, entsize) = struct.unpack_from(
            "<IIQQQQIIQQ", data, off)
        secs.append({"name": name, "typ": typ, "offset": offset, "size": size,
                     "link": link, "entsize": entsize})
    shstr = secs[e_shstrndx]
    for s in secs:
        end = data.index(b"\x00", shstr["offset"] + s["name"])
        s["sname"] = data[shstr["offset"] + s["name"]:end].decode("utf-8", "replace")
    return secs


def read_versions(data, secs):
    need = {}
    for s in secs:
        if s["sname"] != "__versions":
            continue
        for i in range(s["size"] // MODVERSION_ENTRY):
            o = s["offset"] + i * MODVERSION_ENTRY
            (crc,) = struct.unpack_from("<Q", data, o)
            name = data[o + 8:o + MODVERSION_ENTRY].split(b"\x00")[0].decode("utf-8", "replace")
            if name:
                need[name] = crc
    return need


def read_defined(data, secs):
    """模块自身定义的全局符号(用于排除模块间互相提供的符号)。"""
    out = set()
    for s in secs:
        if s["typ"] != SHT_SYMTAB:
            continue
        strtab = secs[s["link"]]
        entsize = s["entsize"] or 24
        for i in range(s["size"] // entsize):
            o = s["offset"] + i * entsize
            (st_name, st_info, st_other, st_shndx) = struct.unpack_from("<IBBH", data, o)
            if st_shndx == SHN_UNDEF or st_name == 0:
                continue
            if (st_info >> 4) not in (1, 2):        # GLOBAL / WEAK
                continue
            end = data.index(b"\x00", strtab["offset"] + st_name)
            out.add(data[strtab["offset"] + st_name:end].decode("utf-8", "replace"))
    return out


def read_vermagic(data):
    marker = b"vermagic="
    i = data.find(marker)
    if i < 0:
        return ""
    return data[i + len(marker):data.index(b"\x00", i)].decode("utf-8", "replace")


def iter_kos(paths):
    for p in paths:
        if os.path.isfile(p) and p.endswith(".ko"):
            yield p
        elif os.path.isdir(p):
            for root, _dirs, files in os.walk(p):
                for f in sorted(files):
                    if f.endswith(".ko"):
                        yield os.path.join(root, f)


def main():
    if len(sys.argv) < 3:
        print(__doc__)
        return 2
    out_path, sources = sys.argv[1], sys.argv[2:]
    need, defined, mods, vermagics = {}, {}, [], {}
    for ko in iter_kos(sources):
        try:
            data = open(ko, "rb").read()
            if data[:4] != b"\x7fELF":
                continue
            secs = elf_sections(data)
            n = read_versions(data, secs)
            d = read_defined(data, secs)
        except Exception as exc:                      # noqa: BLE001
            print(f"  跳过 {ko}: {exc}")
            continue
        rel = os.path.basename(ko)
        mods.append(rel)
        vm = read_vermagic(data)
        vermagics.setdefault(vm, []).append(rel)
        for k, v in n.items():
            need.setdefault(k, v)
        defined.setdefault(rel, d)

    # 模块间提供的符号合集
    provided = set()
    for d in defined.values():
        provided |= d

    lines = [
        "# 魅族21 设备模块(.ko)的 KMI 依赖清单 —— 由 tools/extract_module_kmi.py 生成, 请勿手改",
        "# 用途: CI 编译后用 Module.symvers 校验 NEED 里的每个符号都存在且 CRC 一致,",
        "#       否则内核会拒绝加载厂商模块 → 卡第一屏 2~3 秒后被看门狗重启。",
        f"# 统计: 模块 {len(mods)} 个 / 需要符号 {len(need)} 个 / 模块自身定义 {len(provided)} 个",
    ]
    for vm, names in sorted(vermagics.items()):
        lines.append(f"# vermagic: {vm!r} —— {len(names)} 个模块 (例: {names[0]})")
    lines.append("#")
    for name in sorted(need):
        lines.append(f"NEED 0x{need[name]:08x} {name}")
    lines.append("#")
    for name in sorted(provided):
        lines.append(f"DEF {name}")

    with open(out_path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write("\n".join(lines) + "\n")

    ext = [n for n in need if n not in provided]
    print(f"模块 {len(mods)} 个")
    print(f"__versions 需要的符号 {len(need)} 个, 其中模块间提供 {len(need) - len(ext)} 个 → 必须由内核提供 {len(ext)} 个")
    for vm in vermagics:
        print(f"vermagic: {vm}")
    print(f"已写出 {out_path} ({os.path.getsize(out_path)} 字节)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
