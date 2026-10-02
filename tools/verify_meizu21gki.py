#!/usr/bin/env python3
"""Verify the self-contained MEIZU21GKI repo: workflows + vendored sources.

Checks
  1. 三个 workflow 齐备且 YAML 可解析; build.yml 有 contents:write。
  2. build.yml: LTO 可配置(默认 auto)、extra_config 追加到 DEFCONFIG、
     **两条** LTO 路径都遵循输入。
  3. build.yml: 内置源码优先 —— ReSukiSU 用 $GITHUB_WORKSPACE/kernelsu(带 clone fallback);
     SUSFS 检测 $GITHUB_WORKSPACE/susfs4ksu/kernel_patches 后不再联网克隆;
     KSU/SUSFS 来源元数据支持 .git 与 SOURCE.txt 两种情形。
  4. 失败日志通道 = 仓库 log/ 目录(不再 push build-logs 分支), 且日志 push 不再触发构建。
  5. meizu21.yml: 默认 ReSukiSU / lto none / 三行 extra_config; release 全部 prerelease;
     产物另推 dist 分支; with: 键全部在 build.yml 声明。
  6. 内置目录存在且带 SOURCE.txt; 无 >100MB 单文件(GitHub 限制)。
"""
import os
import sys

import yaml

R = r"C:\work\pt\meizu21-gki\MEIZU21GKI"
W = os.path.join(R, ".github", "workflows")
EXPECT_EXTRA = [
    "# CONFIG_TRIM_UNUSED_KSYMS is not set",
    "# CONFIG_PANIC_ON_OOPS is not set",
    "CONFIG_PANIC_TIMEOUT=30",
]
fail = 0


def check(label, cond, detail=""):
    global fail
    print(f"[{'OK  ' if cond else 'FAIL'}] {label} {detail}")
    if not cond:
        fail += 1


def load(name):
    with open(os.path.join(W, name), encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def shell_text(doc):
    """run: + with.command(retry action) 里的 shell 内容"""
    out = []
    for job in doc["jobs"].values():
        for s in job.get("steps", []) or []:
            if isinstance(s.get("run"), str):
                out.append(s["run"])
            w = s.get("with")
            if isinstance(w, dict) and isinstance(w.get("command"), str):
                out.append(w["command"])
    return "\n".join(out)


def steps_of(doc):
    for job in doc["jobs"].values():
        for s in job.get("steps", []) or []:
            yield s


# ---------- 1. 文件与解析 ----------
for name in ("build.yml", "meizu21.yml", "meizu21-bisect.yml"):
    check(f"{name} 存在", os.path.isfile(os.path.join(W, name)))

b = load("build.yml")
m = load("meizu21.yml")
bis = load("meizu21-bisect.yml")
bblob = shell_text(b)

check("build.yml 有顶层 permissions.contents=write",
      (b.get("permissions") or {}).get("contents") == "write", str(b.get("permissions")))

# ---------- 2. LTO / extra_config ----------
decl = b[True]["workflow_call"]["inputs"]
check("build.yml: lto_mode 默认 auto", decl.get("lto_mode", {}).get("default") == "auto")
check("build.yml: extra_config 默认空", decl.get("extra_config", {}).get("default") == "")
check("build.yml: bazel LTO 用输入",
      'LTO_FLAG="--lto=${{ inputs.lto_mode }}"' in bblob)
check("build.yml: legacy build.sh 也跟随 lto_mode",
      'LEGACY_LTO="${{ inputs.lto_mode }}"' in bblob and 'LTO="$LEGACY_LTO"' in bblob)
check("build.yml: --lto=thin 仅存在于 auto 分支",
      bblob.count("--lto=thin") == 1 and bblob.index('= "auto" ]') < bblob.index("--lto=thin"))
check("build.yml: extra_config 追加到 DEFCONFIG",
      'printf \'%s\\n\' "${{ inputs.extra_config }}" >> "$DEFCONFIG"' in bblob)

# ---------- 3. 内置源码 ----------
check("build.yml: ReSukiSU 使用内置 kernelsu/",
      '"$GITHUB_WORKSPACE/kernelsu/kernel"' in bblob and 'KSU_SRC_DIR=' in bblob)
check("build.yml: 内置缺失时回退官方 setup.sh",
      "ReSukiSU/ReSukiSU/main/kernel/setup.sh" in bblob)
check("build.yml: SUSFS 检测内置 kernel_patches",
      '"$GITHUB_WORKSPACE/susfs4ksu/kernel_patches"' in bblob)
check("build.yml: SUSFS 仍保留联网克隆回退", "gitlab.com/simonpunk/susfs4ksu.git" in bblob)
check("build.yml: KSU/SUSFS 来源支持 SOURCE.txt",
      bblob.count("SOURCE.txt") >= 4)
check("build.yml: 内置 hmbird_patch.c 优先", '"$GITHUB_WORKSPACE/hmbird_patch.c"' in bblob)

# ---------- 4. 失败日志 → log/ ----------
log_steps = [s for s in steps_of(b) if "log/" in str(s.get("name", ""))]
check("build.yml: 失败日志提交到 log/ 目录",
      len(log_steps) == 1 and "sparse-checkout set log" in shell_text(b)
      and "log/${GITHUB_RUN_NUMBER}-run${GITHUB_RUN_ID}" in shell_text(b),
      str([s.get("name") for s in log_steps]))
check("build.yml: 不再 push build-logs 分支", "push -q -f origin build-logs" not in bblob)
FAIL_IF = {"failure()", "${{ failure() }}"}
failure_steps = [s.get("name") for s in steps_of(b) if str(s.get("if")).strip() in FAIL_IF]
check("build.yml: 失败步骤用 failure() 覆盖非编译失败",
      len(failure_steps) >= 3, str(failure_steps))

# ---------- 5. 主入口 workflow ----------
mw = m["jobs"]["build-kernel"]["with"]
check("meizu21.yml: 调用 build.yml", m["jobs"]["build-kernel"]["uses"].endswith("build.yml"))
check("meizu21.yml: 默认 ReSukiSU",
      "ReSukiSU" in str(mw["ksu_variant"]), str(mw["ksu_variant"]))
check("meizu21.yml: lto 默认 none", "none" in str(mw["lto_mode"]), str(mw["lto_mode"]))
extra = [ln.strip() for ln in (mw.get("extra_config") or "").strip().splitlines()]
check("meizu21.yml: extra_config == 期望三行", extra == EXPECT_EXTRA, str(extra))
push = m[True]["push"]
check("meizu21.yml: 触发路径不含 log/**",
      not any(str(p).startswith("log") for p in push["paths"]), str(push["paths"]))
check("meizu21.yml: 触发路径含 kernelsu/ 与 susfs4ksu/",
      "kernelsu/**" in push["paths"] and "susfs4ksu/**" in push["paths"])
rel = shell_text({"jobs": {"r": m["jobs"]["release"]}})
check("meizu21.yml: release 用 --prerelease", rel.count("--prerelease") >= 2)
check("meizu21.yml: 产物推 dist 分支", "dist:dist" in rel)
bad = [k for k in mw if k not in decl]
check("meizu21.yml: with 键全部在 build.yml 声明", not bad, str(bad))

bw = bis["jobs"]["build"]["with"]
bad = [k for k in bw if k not in decl]
check("bisect: with 键全部在 build.yml 声明", not bad, str(bad))
check("bisect: lto 默认 none 且可 dispatch 切换",
      bis[True]["workflow_dispatch"]["inputs"]["lto_mode"]["default"] == "none")
check("bisect: release 为 prerelease",
      "--prerelease" in shell_text({"jobs": {"r": bis["jobs"]["release"]}}))

# ---------- 6. 内置目录与体积 ----------
for d, marker in (("kernelsu", "kernel"), ("susfs4ksu", "kernel_patches"), ("device/meizu21", "dtb")):
    p = os.path.join(R, d)
    check(f"{d}/ 存在且有 SOURCE.txt",
          os.path.isdir(os.path.join(p, marker)) and os.path.isfile(os.path.join(p, "SOURCE.txt")))

# ---------- 6b. vendored 源码完整性(Windows 拷贝会把 symlink 变成文本文件 → 编译找不到 uapi 头) ----------
uapi = os.path.join(R, "kernelsu", "kernel", "include", "uapi", "app_profile.h")
check("kernelsu/kernel/include/uapi/ 是真实目录(不是 Windows 还原的 symlink 文本文件)",
      os.path.isfile(uapi), uapi)
check("kernelsu/manager/.../cpp/uapi/ 已实体化",
      os.path.isfile(os.path.join(R, "kernelsu", "manager", "app", "src", "main", "cpp", "uapi", "app_profile.h")))

mangled = []
for d in ("kernelsu", "susfs4ksu", "device"):
    for root, dirs, files in os.walk(os.path.join(R, d)):
        dirs[:] = [x for x in dirs if x != ".git"]
        for f in files:
            fp = os.path.join(root, f)
            try:
                if os.path.getsize(fp) >= 100:
                    continue
                with open(fp, encoding="utf-8", errors="ignore") as fh:
                    c = fh.read().strip()
            except OSError:
                continue
            if c.startswith(("../", "./")) and "\n" not in c and c.replace("/", "").replace(".", "").isalnum():
                mangled.append((os.path.relpath(fp, R), c))
check("没有『内容为相对路径的小文件』(symlink 被 Windows 还原的残留)", not mangled, str(mangled[:5]))

for d, minimum in (("kernelsu", 595), ("susfs4ksu", 51), ("device/meizu21", 1728)):
    n = sum(len(fs) for _, _, fs in os.walk(os.path.join(R, d)))
    check(f"{d}/ 文件数 >= {minimum}(防再次 vendoring 漏文件)", n >= minimum, f"实际 {n}")

big, total, count = [], 0, 0
for root, dirs, files in os.walk(R):
    dirs[:] = [d for d in dirs if d != ".git"]
    for f in files:
        fp = os.path.join(root, f)
        try:
            sz = os.path.getsize(fp)
        except OSError:
            continue
        total += sz
        count += 1
        if sz > 100 * 1024 * 1024:
            big.append((sz, os.path.relpath(fp, R)))
check("无 >100MB 单文件(GitHub 硬限制)", not big, str(big))
print(f"     仓库工作树: {total/1048576:.1f} MB / {count} 文件")
check("仓库体积 < 900MB(GitHub 建议上限)", total < 900 * 1048576)

print(f"\nRESULT: {'ALL CHECKS PASSED' if fail == 0 else f'{fail} CHECK(S) FAILED'}")
sys.exit(1 if fail else 0)
