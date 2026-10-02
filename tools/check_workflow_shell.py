#!/usr/bin/env python3
"""语法检查: 把每个 workflow 的 run/with.command 抽出来, 去掉 ${{ ... }} 表达式后用 bash -n 验证。

用法: python tools/check_workflow_shell.py [workflows 目录]
需要本机有可用的 bash(WSL: `wsl -e bash`)。仅做语法检查, 不执行。
"""
import os
import re
import subprocess
import sys
import tempfile

import yaml

W = sys.argv[1] if len(sys.argv) > 1 else os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".github", "workflows")

EXPR = re.compile(r"\$\{\{.*?\}\}", re.S)


def to_wsl(path):
    """Windows 路径 → WSL /mnt/<drive>/... 路径"""
    p = os.path.abspath(path)
    drive, rest = os.path.splitdrive(p)
    if not drive:
        return p.replace("\\", "/")
    return "/mnt/" + drive[0].lower() + rest.replace("\\", "/")


def bash_n(path):
    """用 WSL/本地 bash 做 bash -n; 返回 (ok, 输出); ok=None 表示找不到 bash"""
    for cmd in (["wsl", "-e", "bash", "-n", to_wsl(path)], ["bash", "-n", path]):
        try:
            p = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        except (FileNotFoundError, subprocess.TimeoutExpired):
            continue
        out = (p.stdout + p.stderr).strip()
        if p.returncode == 127 or "command not found" in out:
            continue
        return p.returncode == 0, out
    return None, "找不到可用的 bash"


def blocks(doc):
    for job_name, job in doc["jobs"].items():
        for s in job.get("steps", []) or []:
            name = s.get("name") or s.get("uses") or "<unnamed>"
            if isinstance(s.get("run"), str):
                yield f"{job_name}/{name}", s["run"]
            w = s.get("with")
            if isinstance(w, dict) and isinstance(w.get("command"), str):
                yield f"{job_name}/{name} (with.command)", w["command"]


total = bad = 0
tmp = tempfile.mkdtemp(prefix="wfshell")
for fn in sorted(os.listdir(W)):
    if not fn.endswith((".yml", ".yaml")):
        continue
    with open(os.path.join(W, fn), encoding="utf-8") as fh:
        doc = yaml.safe_load(fh)
    if not isinstance(doc, dict) or "jobs" not in doc:
        continue
    for label, script in blocks(doc):
        total += 1
        # ${{ ... }} 是 GitHub 表达式, 不是 bash → 换成占位符再查语法
        cleaned = EXPR.sub("EXPRVAL", script)
        p = os.path.join(tmp, f"{fn}.{total}.sh")
        with open(p, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(cleaned)
        ok, out = bash_n(p)
        if ok is None:
            print(f"[SKIP] {out}")
            sys.exit(2)
        if not ok:
            bad += 1
            print(f"[FAIL] {fn} :: {label}\n{out}")
        else:
            print(f"[OK  ] {fn} :: {label}")

print(f"\nRESULT: {total - bad}/{total} 个 shell 块语法通过" + (f", {bad} 个失败" if bad else ""))
sys.exit(1 if bad else 0)
