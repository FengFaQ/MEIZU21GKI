#!/usr/bin/env python3
"""把 repo manifest 里的 common 项目替换成外部内核树(例如高通 clo/la/kernel/common)。

背景(2026-10 实测结论):
  设备原厂模块导入的符号里, 有 17 个在纯 AOSP ACK 树里 **不存在或未导出**
  (如 scsi_execute_cmd_len / wait_spam_info / mem_cgroup_id_put2 / reclaim_pages /
   pm_system_irq_wakeup 以及 12 个 __tracepoint_android_vh_* 厂商 hook)。
  这些是高通/魅族在自己 fork 的 common 里额外加上的导出, 属于 GKI 保证之外,
  所以纯 AOSP GKI 内核必然加载不了这些厂商模块 → 必须用同源的树来构建。

用法:
  python3 tools/override_manifest_common.py <manifest.xml> --repo clo/la/kernel/common \
      --remote-name qc --remote-fetch https://git.codelinaro.org/ --branch <QC_BRANCH>
"""
import argparse
import re
import shutil
import sys


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("manifest")
    ap.add_argument("--repo", required=True, help="如 clo/la/kernel/common")
    ap.add_argument("--branch", required=True, help="如 ks-kernel.lnx.3.0.c2")
    ap.add_argument("--remote-name", default="qc")
    ap.add_argument("--remote-fetch", default="https://git.codelinaro.org/")
    args = ap.parse_args()

    path = args.manifest
    with open(path, encoding="utf-8") as f:
        xml = f.read()
    shutil.copyfile(path, path + ".orig")

    # 1) 确保存在目标 remote
    if f'name="{args.remote_name}"' not in xml:
        m = re.search(r"<manifest[^>]*>", xml)
        if not m:
            sys.exit("manifest 里找不到 <manifest> 标签")
        xml = (xml[:m.end()]
               + f'\n  <remote name="{args.remote_name}" fetch="{args.remote_fetch}" />'
               + xml[m.end():])
        print(f"[+] 已加入 remote {args.remote_name} -> {args.remote_fetch}")

    # 2) 改写 path="common" 的项目行
    lines = xml.splitlines(keepends=True)
    hit = 0
    for i, line in enumerate(lines):
        if "<project" in line and 'path="common"' in line:
            new = re.sub(r'name="[^"]*"', f'name="{args.repo}"', line, count=1)
            if 'remote="' in new:
                new = re.sub(r'remote="[^"]*"', f'remote="{args.remote_name}"', new, count=1)
            else:
                new = re.sub(r'(name="[^"]*")', rf'\1 remote="{args.remote_name}"', new, count=1)
            if 'revision="' in new:
                new = re.sub(r'revision="[^"]*"', f'revision="{args.branch}"', new, count=1)
            else:
                new = re.sub(r'(name="[^"]*")', rf'\1 revision="{args.branch}"', new, count=1)
            lines[i] = new
            hit += 1
            print(f"[+] {line.strip()}\n -> {new.strip()}")
    if not hit:
        sys.exit('manifest 里找不到 path="common" 的项目 —— 拒绝继续(否则会静默构建原树)')

    with open(path, "w", encoding="utf-8") as f:
        f.write("".join(lines))
    print(f"[+] 已改写 {path} (原文件备份为 {path}.orig)")


if __name__ == "__main__":
    main()
