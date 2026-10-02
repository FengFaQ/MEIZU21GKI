#!/usr/bin/env python3
"""从参考镜像(resukisu-boot.img)里把可核查的事实全部导出成文本, 便于向原作者求证。

用法: python tools/extract_ref_report.py <boot.img 或 kernel 文件> <输出目录>
产出:
  <输出目录>/reference.config        内嵌 IKCONFIG 完整 .config
  <输出目录>/reference_strings.txt   版本串 / KSU 相关串 / 64位hex 哈希
  <输出目录>/reference_keys.txt      关键 CONFIG 项(逐条, 带 "未设置" 标记)
  <输出目录>/reference_summary.txt   汇总(含 sha256 / 大小)
"""
import hashlib
import os
import re
import sys
import zlib

KEY_PAT = re.compile(r"^(CONFIG_[A-Z0-9_]+)=(.*)$|^# (CONFIG_[A-Z0-9_]+) is not set$", re.M)
PREFIXES = ("CONFIG_LTO", "CONFIG_TRIM", "CONFIG_PANIC", "CONFIG_IKCONFIG", "CONFIG_LOCALVERSION",
            "CONFIG_KSU", "CONFIG_KALLSYMS", "CONFIG_MODULE_SIG", "CONFIG_DEBUG_INFO",
            "CONFIG_CFI", "CONFIG_SHADOW_CALL_STACK", "CONFIG_RANDOMIZE", "CONFIG_MODULE_COMPRESS",
            "CONFIG_UNUSED_KSYMS", "CONFIG_TRIM_UNUSED")


def find_ikconfig(data: bytes):
    pos, out = 0, []
    while True:
        pos = data.find(b"\x1f\x8b", pos)
        if pos < 0:
            return out
        try:
            blob = zlib.decompressobj(31).decompress(data[pos:])
        except Exception:
            pos += 1
            continue
        if len(blob) > 100_000 and b"CONFIG_" in blob[:4096]:
            out.append(blob)
            if len(out) >= 2:
                return out
        pos += 1


def main(path, outdir):
    os.makedirs(outdir, exist_ok=True)
    data = open(path, "rb").read()
    lines = []
    add = lines.append

    add(f"输入文件: {path}")
    add(f"大小: {len(data)} 字节")
    add(f"SHA256: {hashlib.sha256(data).hexdigest()}")

    versions = sorted({m.decode() for m in re.findall(rb"Linux version [ -~]{5,160}", data)})
    add("\n== Linux version 串 ==")
    for v in versions:
        add("  " + v)

    add("\n== KSU / SUSFS / 变体 相关可打印串 ==")
    pats = [rb"[ -~]{0,30}(?:ReSukiSU|SukiSU|KernelSU|KoWSU)[ -~]{0,50}",
            rb"[ -~]{0,30}huahua[ -~]{0,40}",
            rb"[ -~]{0,20}KSU_VERSION[ -~]{0,30}",
            rb"[ -~]{0,25}susfs[ -~]{0,45}"]
    seen = set()
    for p in pats:
        for m in re.findall(p, data):
            s = m.decode("utf-8", "replace")
            if s not in seen:
                seen.add(s)
                add("  " + s)

    hashes = sorted({m.decode() for m in re.findall(rb"\b[0-9a-f]{64}\b", data)})
    add(f"\n== 镜像内出现的 64 位 hex 串(共 {len(hashes)}) — 管理器签名证书哈希候选 ==")
    for h in hashes:
        add("  " + h)

    blobs = find_ikconfig(data)
    add(f"\n== 内嵌 IKCONFIG(.config) 数量: {len(blobs)} ==")
    if blobs:
        cfg = blobs[0].decode("utf-8", "replace")
        with open(os.path.join(outdir, "reference.config"), "w", encoding="utf-8", newline="\n") as fh:
            fh.write(cfg)
        kv = {}
        for a, b, c in KEY_PAT.findall(cfg):
            if a:
                kv[a] = b
            elif c:
                kv[c] = "n"
        add(f"内嵌 .config 行数: {cfg.count(chr(10))} / 解析出配置项: {len(kv)}")

        with open(os.path.join(outdir, "reference_keys.txt"), "w", encoding="utf-8", newline="\n") as fh:
            fh.write("== 参考镜像内嵌 .config 关键项(逐条) ==\n")
            for k in sorted(kv):
                if k.startswith(PREFIXES):
                    fh.write(f"{k}={kv[k]}\n")
            fh.write("\n== 与 KSU/SUSFS 有关但值为 n 的项 ==\n")
            for k in sorted(kv):
                if ("KSU" in k or "SUSFS" in k) and kv[k] == "n":
                    fh.write(f"# {k} is not set\n")

        add("\n== 关键项(节选) ==")
        for k in ("CONFIG_LTO_NONE", "CONFIG_LTO_CLANG_THIN", "CONFIG_LTO_CLANG",
                  "CONFIG_TRIM_UNUSED_KSYMS", "CONFIG_PANIC_ON_OOPS", "CONFIG_PANIC_TIMEOUT",
                  "CONFIG_IKCONFIG", "CONFIG_LOCALVERSION", "CONFIG_KSU",
                  "CONFIG_KSU_MULTI_MANAGER_SUPPORT", "CONFIG_KSU_SUSFS_HAS_MAGIC_MOUNT",
                  "CONFIG_KSU_SUSFS", "CONFIG_KSU_FULL_NAME_FORMAT", "CONFIG_KSU_FEATURE_ADBROOT"):
            add(f"  {k} = {kv.get(k, '<该项在 .config 中不存在>')}")
        add("  (完整关键项见 reference_keys.txt)")

        with open(os.path.join(outdir, "reference_strings.txt"), "w", encoding="utf-8", newline="\n") as fh:
            fh.write("\n".join(lines) + "\n")

    with open(os.path.join(outdir, "reference_summary.txt"), "w", encoding="utf-8", newline="\n") as fh:
        fh.write("\n".join(lines) + "\n")
    print("\n".join(lines))


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
