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
import re
import sys

import yaml

R = r"C:\work\pt\meizu21-gki\MEIZU21GKI"
W = os.path.join(R, ".github", "workflows")
EXPECT_EXTRA = [
    "# CONFIG_TRIM_UNUSED_KSYMS is not set",
    "# CONFIG_PANIC_ON_OOPS is not set",
    "# 允许 adb shell dmesg 读取内核日志(否则 user 版构建下 shell 无权读, 排障只能靠抢 512K",
    "# 环形缓冲区的开机瞬间 —— 本次黑屏问题正是靠这个手段才定位到 msm_kgsl 的符号 CRC 失配)。",
    "# 只影响权限位, 不涉及任何导出符号/KMI。",
    "# CONFIG_SECURITY_DMESG_RESTRICT is not set",
    "CONFIG_PANIC_TIMEOUT=30",
    # ★ 2026-10-03: 恢复原厂取值 / 去掉空转的 zram 模块
    # (只列 CONFIG_ 行做子集比对, 注释行不逐一比对, 避免文案微调就报错)
    # ※ TMPFS_XATTR / TMPFS_POSIX_ACL 不在此列: 它们是 CI 为 KernelSU 主动开的, 见下方冲突检查
    "# CONFIG_DAMON is not set",
    "# CONFIG_BLK_CGROUP_IOPRIO is not set",
    "# CONFIG_ZRAM is not set",
    "# CONFIG_ZSMALLOC is not set",
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
check("meizu21.yml: lto 默认 none (与原厂一致; CFI 不依赖 LTO, 见 build.yml 的 shrink_slab 修复)",
      "none" in str(mw["lto_mode"]), str(mw["lto_mode"]))
extra = [ln.strip() for ln in (mw.get("extra_config") or "").strip().splitlines()]
_missing = [e for e in EXPECT_EXTRA if e not in extra]
check("meizu21.yml: extra_config 覆盖全部期望配置项", not _missing, "missing=%s" % _missing)

# ---------- 2b. kleaf fragment 校验的两个坑(run 15 实际编译失败两次) ----------
# ① fragment 是用 "diff gki_defconfig.orig gki_defconfig | grep '^>'" 生成的, 所以 extra_config
#    块内每一行都会原样进入 fragment。
# ② kleaf 的校验器会把【注释行】连同紧跟的那行 config 一起当成该符号的"期望值"文本;
#    如果注释里出现了 CONFIG_XXX 字样就会被粘连, 报
#      expected '# ... CONFIG_DAMON select,\n# CONFIG_DAMON is not set'
#    => 块内注释行禁止出现 CONFIG_XXX 字样。
_bad_cmt = [ln for ln in extra
            if ln.startswith("#") and "CONFIG_" in ln and not ln.startswith("# CONFIG_")]
check("meizu21.yml: extra_config 注释行不得含 CONFIG_XXX 字样(kleaf 会粘连)",
      not _bad_cmt, str(_bad_cmt))
# ③ 同一符号两条相反声明 -> 校验器报 expected 里同时有两行, 判定自相矛盾。
#    典型: CI 的「配置内核选项」步骤已 append CONFIG_TMPFS_XATTR=y。
_syms = {}
_dup = []
for _ln in extra:
    if _ln.startswith("# CONFIG_") and _ln.endswith(" is not set"):
        _s, _v = _ln[2:-len(" is not set")].strip(), "n"
    elif _ln.startswith("CONFIG_") and "=" in _ln:
        _s, _v = _ln.split("=", 1)
    else:
        continue
    if _s in _syms and _syms[_s] != _v:
        _dup.append(_s)
    _syms[_s] = _v
check("meizu21.yml: extra_config 同一符号不得有相反声明", not _dup, str(_dup))
# ④ 与 build.yml 里硬写进 DEFCONFIG 的符号交叉检查, 保证上面那条不会因为改别处而失效。
_forced = set()
for _st in steps_of(b):
    # 只统计【无条件】步骤: 带 if 的步骤(如 use_zram 控制的 ZRAM 补丁栈)本次不会执行, 不算强制打开
    if _st.get("if"):
        continue
    _txt = _st.get("run") or ""
    _w = _st.get("with") or {}
    if isinstance(_w.get("command"), str):
        _txt += "\n" + _w["command"]
    for _m in re.findall(r'^CONFIG_([A-Z0-9_]+)=', _txt, re.M):
        _forced.add("CONFIG_" + _m)
_conflict = sorted(s for s, v in _syms.items() if v == "n" and s in _forced)
check("meizu21.yml: extra_config 关掉的符号不与 build.yml 强制打开的冲突",
      not _conflict, "conflict=%s" % _conflict)
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

# ---------- 6c. vendor 模块 vermagic + boot 头部 os_version(两个"进 fastboot / 重启"根因) ----------
STOCK_VERSION = "6.1.25-android14-11-maybe-dirty"
check("build.yml: 声明 boot_sign 输入(默认签名, 保持其它机型旧行为)",
      decl.get("boot_sign", {}).get("default") == "签名", str(decl.get("boot_sign")))
check("meizu21.yml: version == 原厂 LOCALVERSION(否则厂商模块拒绝加载)",
      mw.get("version") == STOCK_VERSION, str(mw.get("version")))
check("bisect: version == 原厂 LOCALVERSION", bw.get("version") == STOCK_VERSION, str(bw.get("version")))
check("meizu21.yml: boot_sign 不签名(对齐可启动参考镜像)",
      mw.get("boot_sign") == "不签名", str(mw.get("boot_sign")))
check("bisect: boot_sign 不签名", bw.get("boot_sign") == "不签名", str(bw.get("boot_sign")))
check("build.yml: Android13+ 分支写 os_version/os_patch_level(缺失会被 ABL 判非法→fastboot)",
      '--os_version "$OS_VERSION" --os_patch_level "$OS_PATCH"' in bblob)
check("build.yml: Android13+ 分支 os_version 由 android_version 推导",
      'ANDROID_MAJOR=$(echo "${{ inputs.android_version }}" | tr -dc \'0-9\')' in bblob)
check("build.yml: 不签名时零填充到分区大小(清掉分区尾部旧 AVB footer)",
      'truncate -s "$PART_SIZE" "$OUT"' in bblob)
# ★ 2026-10-03: 原厂 boot.img 正好 100663296 字节(= boot 分区大小 = 96 MiB)。
#   之前填 64 MiB, 短了 32 MiB -> fastboot 只写 64 MiB, 分区尾部 32 MiB 保留上一次刷入的数据,
#   连原厂放在"分区末尾-64"处的 AVB footer("AVBf" @0x5ffffc0)都还在。
check("build.yml: PART_SIZE == 原厂 boot.img 大小 96 MiB (100663296)",
      "PART_SIZE=$((96 * 1024 * 1024))" in bblob,
      "need PART_SIZE=$((96 * 1024 * 1024))")
check("build.yml: PART_SIZE 不再用旧的 64 MiB", "PART_SIZE=$((64 * 1024 * 1024))" not in bblob)
check("build.yml: boot.img 结构自检(大小/头部/无 cmdline)存在",
      "BOOT IMG CHECK PASSED" in bblob and "100663296" in bblob)
check("build.yml: boot.img cmdline 为空(原厂也是空; cmdline 会进 bootconfig 而非此处)",
      'CMDLINE=""' in bblob)
check("tools/bootcompare.py 存在(boot 镜像结构分析工具)", os.path.isfile(os.path.join(R, "tools", "bootcompare.py")))
check("build.yml: 版本串校验不匹配时硬失败(不产出坏包)",
      "内核版本串不匹配" in bblob and bblob.count("exit 1") >= 1)
check("build.yml: 打印 vermagic 便于核对", "SMP preempt mod_unload modversions aarch64" in bblob)

# ---------- 6d. 厂商模块 KMI(符号 CRC)兼容性自检 ----------
man = os.path.join(R, "device", "meizu21", "module_kmi_manifest.txt")
need = defs = 0
if os.path.isfile(man):
    with open(man, encoding="utf-8") as fh:
        for line in fh:
            need += line.startswith("NEED ")
            defs += line.startswith("DEF ")
check("device/meizu21/module_kmi_manifest.txt 存在且规模合理",
      need >= 2800 and defs >= 800, f"NEED={need} DEF={defs}")
check("tools/check_module_kmi.py 存在", os.path.isfile(os.path.join(R, "tools", "check_module_kmi.py")))
for _t in ("extract_module_kmi.py", "analyze_boot_image.py", "check_loadlist.py"):
    check(f"tools/{_t} 存在(诊断工具随仓库走)", os.path.isfile(os.path.join(R, "tools", _t)))
check("build.yml: 编译后跑厂商模块 KMI 校验",
      "tools/check_module_kmi.py" in bblob and "module_compat.txt" in bblob)
check("build.yml: KMI 报告与 symvers 随产物上传",
      "module_compat.txt" in bblob and "cp \"$SYMVERS\" \"$GITHUB_WORKSPACE/Module.symvers\"" in bblob)
check("build.yml: KMI 校验失败时会告警",
      "厂商模块可能加载失败" in bblob)
# KERNEL_ROOT 来自 $GITHUB_ENV。实务上 `working-directory: ${{ env.KERNEL_ROOT }}` 能解析
# (全流水线 20 处都这么用且构建成功), 但新步骤统一用 shell 变量 + 兜底, 更稳且可读。
new_steps = {str(s.get("name")): s for s in steps_of(b)
             if "版本串" in str(s.get("name")) or "KMI 兼容" in str(s.get("name"))}
check("build.yml: 版本串校验 / KMI 校验步骤存在", len(new_steps) == 2, str(list(new_steps)))
_bad = [n for n, s in new_steps.items() if "${{ env.KERNEL_ROOT }}" in str(s.get("run", ""))]
check("build.yml: 新步骤内不用 ${{ env.KERNEL_ROOT }}(用 shell 变量)",
      not _bad, str(_bad))
check("build.yml: 新步骤有 KERNEL_ROOT 兜底默认值",
      all(': "${KERNEL_ROOT:=$GITHUB_WORKSPACE/$CONFIG}"' in str(s.get("run", ""))
          for s in new_steps.values()))

print(f"\nRESULT: {'ALL CHECKS PASSED' if fail == 0 else f'{fail} CHECK(S) FAILED'}")
sys.exit(1 if fail else 0)
