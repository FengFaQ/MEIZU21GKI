#!/usr/bin/env python3
"""把 CI 报出的 CRC 不一致/缺失符号, 与 ACK 的 GKI KMI 符号表对照。

结论意义:
  * 若不一致符号 **不在** KMI 表里 → 它们是 GKI 保证之外的符号(只有高通在自己树里维持其 CRC 稳定),
    所以换任意 ACK 版本都可能对不上 → 必须用与设备同源的树(或强制对齐 CRC)。
  * 若在 KMI 表里 → 说明 Google 保证的 ABI 也变了 → 更可能是我们构建/源码选择有误。
"""
import os
import re
import subprocess
import sys

ROOT = r"C:\work\pt\meizu21-gki"
ACK = os.path.join(ROOT, r"work\kmicmp\ack2023-10")
REPORT = os.path.join(ROOT, r"work\dist8\module_compat.txt")


def git(*args):
    r = subprocess.run(["git", "-C", ACK, *args], capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    return r.stdout


print("=== ACK 树 android/ 下的文件 ===")
print(git("ls-tree", "--name-only", "HEAD", "android/"))

# 找出 KMI 符号表(可能叫 abi_gki_aarch64 / *_symbol_list 等)
cands = [f for f in git("ls-tree", "-r", "--name-only", "HEAD", "android/").splitlines()
         if "abi_gki_aarch64" in f and not f.endswith((".xml", ".stg", ".json"))]
print("候选 KMI 表:", cands)

kmi = set()
for c in cands:
    txt = git("show", f"HEAD:{c}")
    for line in txt.splitlines():
        line = line.strip()
        if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", line):
            kmi.add(line)
print(f"KMI 符号总数(合并): {len(kmi)}")

# 解析 CI 报告
bad = []
if os.path.exists(REPORT):
    for line in open(REPORT, encoding="utf-8", errors="replace"):
        m = re.match(r"^\s*(MISSING|MISMATCH|缺失|不一致)\s+(\S+)", line)
        if m:
            bad.append((m.group(1), m.group(2)))
        else:
            m2 = re.search(r"\b([A-Za-z_][A-Za-z0-9_]*)\b", line)
            if line.strip().startswith(("MISSING", "MISMATCH")):
                bad.append(("?", line.split()[-1]))
if not bad:
    # 兜底: 报告里所有 0x 开头的行
    for line in open(REPORT, encoding="utf-8", errors="replace"):
        m = re.search(r"(0x[0-9a-fA-F]{8})\s+(\S+)", line)
        if m:
            bad.append(("CRC", m.group(2)))
print(f"\n从 {os.path.basename(REPORT)} 解析出可疑符号 {len(bad)} 个")
print("报告前 30 行:")
for line in open(REPORT, encoding="utf-8", errors="replace").read().splitlines()[:30]:
    print("   ", line)
