#!/usr/bin/env python3
"""比较两棵内核树(BLOB 哈希, 只取树对象, 不下载整树)找出头文件差异。

用途: 判断"我们的 ACK 源码"与"设备内核所用的高通 common 源码"是否在 KMI 结构上不同,
从而区分 KMI CRC 差异来自 **源码树** 还是 **构建参数/配置**。

用法:
  python tools/cmp_ack_qc_headers.py --a <dirA> --b <dirB> [--paths include/linux ...]
                                    [--dump 12] [--key include/net/sock.h ...]
"""
import argparse
import os
import subprocess
import sys

KEY_FILES = [
    "include/net/sock.h", "include/linux/net.h", "include/linux/dma-buf.h",
    "include/drm/drm_gem.h", "include/linux/shrinker.h", "include/linux/fs.h",
    "include/linux/mm_types.h", "include/linux/device.h", "include/linux/android_kabi.h",
    "include/linux/export.h", "include/linux/kernfs.h", "include/linux/blk_types.h",
    "include/linux/mm.h", "include/linux/sched.h", "include/linux/cgroup-defs.h",
    "include/linux/socket.h", "include/linux/module.h", "include/linux/utsname.h",
]


def git(repo, *args):
    r = subprocess.run(["git", "-C", repo, *args], capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    if r.returncode != 0:
        sys.stderr.write(f"[git {' '.join(args)}] {r.stderr.strip()}\n")
    return r.stdout


def tree_map(repo, paths):
    out = git(repo, "ls-tree", "-r", "HEAD", "--", *paths)
    m = {}
    for line in out.splitlines():
        try:
            meta, path = line.split("\t", 1)
            mode, typ, sha = meta.split()
        except ValueError:
            continue
        if typ == "blob":
            m[path] = sha
    return m


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--a", required=True)
    ap.add_argument("--b", required=True)
    ap.add_argument("--paths", nargs="*", default=["include/linux", "include/net", "include/drm",
                                                   "include/scsi", "include/crypto", "include/keys",
                                                   "kernel", "mm", "fs", "drivers/dma-buf",
                                                   "drivers/scsi", "drivers/ufs", "security"])
    ap.add_argument("--dump", type=int, default=8, help="对多少个关键文件输出内容差异")
    ap.add_argument("--dump-all-key", action="store_true")
    args = ap.parse_args()

    a, b = args.a, args.b
    print(f"A(我们/ACK) HEAD = {git(a, 'rev-parse', 'HEAD').strip()}")
    print(f"B(设备/QC ) HEAD = {git(b, 'rev-parse', 'HEAD').strip()}")
    ma = tree_map(a, args.paths)
    mb = tree_map(b, args.paths)
    print(f"文件数: A={len(ma)}  B={len(mb)}")

    only_a = sorted(set(ma) - set(mb))
    only_b = sorted(set(mb) - set(ma))
    diff = sorted(p for p in set(ma) & set(mb) if ma[p] != mb[p])
    print(f"\n只 A 有: {len(only_a)}   只 B 有: {len(only_b)}   内容不同: {len(diff)}")
    if only_b:
        print("  B 独有(前 30):", *only_b[:30], sep="\n    ")
    if diff:
        print("  内容不同(按目录统计):")
        from collections import Counter
        c = Counter(os.path.dirname(p) for p in diff)
        for d, n in c.most_common(25):
            print(f"    {n:4d}  {d}")

    key = list(KEY_FILES)
    print("\n===== 关键结构体头文件 =====")
    for p in key:
        sa, sb = ma.get(p), mb.get(p)
        if sa is None and sb is None:
            print(f"  {p:34s} 两边都没有")
            continue
        if sa is None:
            print(f"  {p:34s} 只有 B 有")
            continue
        if sb is None:
            print(f"  {p:34s} 只有 A 有")
            continue
        print(f"  {p:34s} {'相同 ✓' if sa == sb else '**不同 ✗**'}")

    todo = [p for p in key if ma.get(p) and mb.get(p) and ma[p] != mb[p]]
    if not args.dump_all_key:
        todo = todo[:args.dump]
    for p in todo:
        print(f"\n########## diff {p}  (A=ACK  B=QC) ##########")
        ta = git(a, "show", f"HEAD:{p}")
        tb = git(b, "show", f"HEAD:{p}")
        import difflib
        d = list(difflib.unified_diff(ta.splitlines(), tb.splitlines(),
                                      fromfile=f"A/{p}", tofile=f"B/{p}", n=3, lineterm=""))
        if not d:
            print("  (内容一致, 但 blob 不同 —— 可能只是空白/属性)")
        for line in d[:400]:
            print(line)
        if len(d) > 400:
            print(f"  ...(还有 {len(d) - 400} 行)")


if __name__ == "__main__":
    main()
