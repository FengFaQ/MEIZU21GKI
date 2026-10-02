#!/usr/bin/env python3
"""用内核 Module.symvers 校验"设备模块清单里的符号能不能加载"。

判定规则(与内核 module/main.c 的 check_modinfo / same_magic 一致):
  * 模块带 __versions 段(CONFIG_MODVERSIONS=y)时, 内核只比对首个空格之后的部分,
    即 **版本串(含 LOCALVERSION)不参与比对, 符号 CRC 才是真校验**;
  * 因此这里逐个检查清单里 NEED 的符号: 名字在 Module.symvers 里存在, 且 CRC 低 32 位一致;
  * 清单里 DEF 的符号是设备模块互相提供的, 不算缺失。

用法:
  python tools/check_module_kmi.py --manifest device/meizu21/module_kmi_manifest.txt \
      --symvers Module.symvers --report module_compat.txt [--fail-on-missing]
"""
import argparse
import os
import sys


def load_symvers(path):
    out = {}
    if not os.path.isfile(path):
        return out
    with open(path, encoding="utf-8", errors="replace") as fh:
        for line in fh:
            parts = line.rstrip("\n").split("\t")
            if len(parts) < 2:
                continue
            crc, name = parts[0].strip(), parts[1].strip()
            try:
                out[name] = int(crc, 16)
            except ValueError:
                continue
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--manifest", required=True)
    ap.add_argument("--symvers", required=True)
    ap.add_argument("--report", required=True)
    ap.add_argument("--sample", type=int, default=50)
    ap.add_argument("--fail-on-missing", action="store_true")
    args = ap.parse_args()

    need, provided = {}, set()
    for line in open(args.manifest, encoding="utf-8"):
        if line.startswith("NEED "):
            bits = line.split(None, 2)
            if len(bits) == 3:
                need[bits[2].strip()] = int(bits[1], 16)
        elif line.startswith("DEF "):
            provided.add(line.split(None, 1)[1].strip())

    if not need:
        print("清单为空, 跳过")
        return 0
    kv = load_symvers(args.symvers)
    if not kv:
        print(f"Module.symvers 读取失败或为空: {args.symvers}")
        return 0

    missing, mismatch, ok = [], [], 0
    for name, crc in sorted(need.items()):
        if name in provided:
            continue
        got = kv.get(name)
        if got is None:
            missing.append((name, crc))
        elif (got & 0xFFFFFFFF) != (crc & 0xFFFFFFFF):
            mismatch.append((name, crc, got))
        else:
            ok += 1

    checkable = ok + len(missing) + len(mismatch)
    out = [
        "# 厂商模块 KMI 兼容性报告(内核 Module.symvers vs 设备模块 __versions)",
        f"# 清单: {args.manifest}",
        f"# 内核: {args.symvers}",
        f"# 需要内核提供且可校验的符号: {checkable} 个",
        f"# 一致: {ok} / 缺失: {len(missing)} / CRC 不一致: {len(mismatch)}",
        "",
    ]
    if not missing and not mismatch:
        out.append("RESULT: OK —— 设备模块需要的符号全部存在且 CRC 一致, 内核可以加载厂商模块")
    else:
        out.append("RESULT: FAIL —— 存在无法加载的厂商模块(内核会打印 "
                   "'disagrees about version of symbol' 或 'Unknown symbol')")
        if missing:
            out.append(f"\n== 缺失符号(内核没导出) 共 {len(missing)} 个, 前 {args.sample} 个 ==")
            out += [f"MISSING 0x{crc:08x} {name}" for name, crc in missing[:args.sample]]
        if mismatch:
            out.append(f"\n== CRC 不一致 共 {len(mismatch)} 个, 前 {args.sample} 个 ==")
            out += [f"MISMATCH 期望 0x{crc:08x} 实际 0x{got:08x} {name}"
                    for name, crc, got in mismatch[:args.sample]]
    text = "\n".join(out) + "\n"
    with open(args.report, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(text)
    print(text)
    if args.fail_on_missing and (missing or mismatch):
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
