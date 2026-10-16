#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# 10_ksu_input_hook_early_retire.sh
#
# 让 ReSukiSU 的 SUSFS 输入钩子尽早退休, 并去掉自旋锁(原子上下文)里的 pr_info。
#
# 为什么用脚本而不是 .patch:
#   构建时 ReSukiSU 是【现场从 GitHub 克隆】的 (build.yml 的 KSU_REPO/KSU_REF),
#   仓库内置的 kernelsu/ 目录已不参与编译 —— 改内置目录无效。克隆树路径是
#   $KSU_DIR, 用 .patch 会因 -p 层级与 fuzz 不稳; 这里做精确字符串替换,
#   幂等 + 自校验, 且不使用 python (CI 与本地环境都能跑)。
#
# 用法:  10_ksu_input_hook_early_retire.sh <KernelSU 源码根目录>
#
# ⚠️ 定位说明: 本脚本修的是两个【真实但轻微】的缺陷。按现有证据它们
#    【不足以解释】用户反馈的"打游戏时像鼠标双击/长按"(见 docs/ 下的诊断报告)。
#    本脚本的作用是"消除内核在输入热路径上的唯一差异 + 修掉原子上下文里的日志",
#    属于降低变量, **不是已验证的修复**。
# ---------------------------------------------------------------------------
set -euo pipefail

KSU_DIR="${1:-}"
if [ -z "$KSU_DIR" ] || [ ! -d "$KSU_DIR" ]; then
    echo "::error::10_ksu_input_hook_early_retire: 未提供有效的 KernelSU 源码目录 (收到: '$KSU_DIR')"
    exit 1
fi

TARGET="$KSU_DIR/kernel/runtime/ksud_integration.c"
if [ ! -f "$TARGET" ]; then
    echo "::error::找不到 $TARGET -- ReSukiSU 上游目录结构可能已变, 请复核本脚本"
    exit 1
fi

echo "--- 10_ksu_input_hook_early_retire: 目标 $TARGET"

# 幂等: 已打过就跳过
if grep -q 'input_hook_retire_pending' "$TARGET"; then
    echo "    已打过 (发现 input_hook_retire_pending), 跳过"
    exit 0
fi

# 先校验四个锚点都在, 少一个就中止 (避免半改)
grep -q 'static unsigned int volumedown_pressed_count = 0;' "$TARGET" \
    || { echo "::error::锚点1缺失: volumedown_pressed_count 声明"; exit 1; }
grep -q 'pr_info("KEY_VOLUMEDOWN val: %d' "$TARGET" \
    || { echo "::error::锚点2缺失: 输入钩子里的 pr_info"; exit 1; }
grep -q '^\s*// stop hook first!' "$TARGET" \
    || { echo "::error::锚点3缺失: ksu_is_safe_mode 的 stop hook 注释"; exit 1; }
grep -q '^\s*input_hook_stopped = true;' "$TARGET" \
    || { echo "::error::锚点4缺失: ksu_stop_input_hook_runtime 主体"; exit 1; }

cp "$TARGET" "$TARGET.orig"

# ---- 1) 在 volumedown_pressed_count 声明后插入 pending 标志 ----------------
awk '
/^static unsigned int volumedown_pressed_count = 0;$/ {
    print
    print ""
    print "// Set from atomic (input spinlock) context once the volume-down threshold is"
    print "// reached; consumed by non-atomic callers that are allowed to sleep."
    print "static bool input_hook_retire_pending = false;"
    next
}
{ print }
' "$TARGET.orig" > "$TARGET"

# ---- 2) 去掉自旋锁内的 pr_info ---------------------------------------------
sed -i 's|^\(\s*\)pr_info("KEY_VOLUMEDOWN val: %d\\n", val);$|\1// NOTE: this runs inside the input device spinlock (atomic context).\n\1// pr_info() here would take the console/logbuf locks on every single\n\1// volume-down event, so it is deliberately not used. Count only.|' "$TARGET"

# ---- 3) ksu_is_safe_mode(): 补充说明 (它本来就退休钩子, 只是写得含糊) ------
sed -i 's|^\(\s*\)// stop hook first!$|\1// Userspace asked about safe mode, which means boot has progressed far\n\1// enough that the volume-down counter can no longer grow in a way that\n\1// matters. Retire the input hook here as well, so the input_handle_event()\n\1// call site becomes a single predictable branch as early as possible.|' "$TARGET"

# ---- 4) ksu_stop_input_hook_runtime(): 清 pending 标志 ---------------------
awk '
/^[[:space:]]*input_hook_stopped = true;$/ {
    print
    print "    input_hook_retire_pending = false;"
    next
}
{ print }
' "$TARGET" > "$TARGET.tmp" && mv "$TARGET.tmp" "$TARGET"

# ---- 自校验 ----------------------------------------------------------------
fail=0
grep -q 'static bool input_hook_retire_pending = false;' "$TARGET" || { echo "::error::自校验失败: 未插入 pending 标志"; fail=1; }
grep -q 'pr_info("KEY_VOLUMEDOWN val' "$TARGET" && { echo "::error::自校验失败: 自旋锁内的 pr_info 仍在"; fail=1; }
grep -q 'input_hook_retire_pending = false;' "$TARGET" || { echo "::error::自校验失败: 未在 stop 里清标志"; fail=1; }

if [ "$fail" -ne 0 ]; then
    echo "::error::10_ksu_input_hook_early_retire 失败, 已回滚"
    mv "$TARGET.orig" "$TARGET"
    exit 1
fi

rm -f "$TARGET.orig"
echo "    自校验通过: 输入钩子早退标志已插入 + 原子上下文日志已移除"
