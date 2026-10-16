# 触控问题诊断归档 (run 23)

> 起因: 用户反馈"就打游戏的时候会触发类似鼠标双击和长按。"
> 对象: release `meizu21-sukisu-23` (run #23 / `37096230203` / commit `cd9372ac`)

## 文件

| 文件 | 说明 |
| --- | --- |
| `触控问题诊断报告-run23.md` | **主报告**。完整证据链、排除项、可执行的排查/验证步骤 |
| `touch-analysis/a64dis.py` | 自研轻量 AArch64 反汇编器（无需 objdump；用于证实手势分发通路） |
| `touch-analysis/kcfi_expect.py` | 抽厂商模块在每个间接调用点写死的 KCFI 期望哈希 |
| `touch-analysis/kcfi_coverage.py` | 统计内核里是否存在这些哈希作为"函数入口类型哈希" |

## 结论速览

**已排除（有证据）**

| 项 | 结论 |
| --- | --- |
| run 23 是否引入回归 | ❌ 否。run22 与 run23 的内核二进制等价（源码只差 CI 断言 + 2 个不参与编译的工具） |
| KMI / CRC 层 | ✅ 健康。设备 4891 个符号：**0 个 CRC 不匹配、0 个无法解析** |
| KCFI（CFI 类型哈希）层 | ✅ 与原厂内核**等价**（对照组实验：`goodix_ts` 4/18 两边相同） |
| 触摸模块依赖 / 加载顺序 | ✅ 无问题。依赖闭包 6 个模块、缺失 0；`modules.load` 顺序本非权威（libmodprobe 按 `modules.dep` 拓扑排序） |
| SUSFS / KSU 干扰输入 | ❌ 否。SUSFS 确实 hook 了 `input_handle_event`，但实现**只读** `KEY_VOLUMEDOWN` 计数、**从不改写** type/code/value，且 `post-fs-data` 即关闭 |
| 触摸固件是否缺失 | ✅ 不缺失。`/vendor/firmware/goodix_*.bin` 实测存在于原厂 vendor；run23 只换 boot 分区（`anykernel.sh`: `do.modules=0`），Flyme 系统侧完整保留 |

**当前最强线索（vendor 侧，非内核）**

`goodix_ts.ko` 内建游戏模式：Flyme 用户态按**游戏包名**写 `game_mode_node`
（原厂 `super.img` 内实测存在该路径模板、`game_mode_intervention.list`、连 PUBG 的配置都有），
驱动据此把 `Game_*_screen_*_buff` / `Horizontal_screen_left/right_buff`
这类**边缘分区配置**烧进触摸 IC，从而改变触摸判读 —— 与"一次按压被拆成多次 / 被保持"
（即用户说的双击 + 长按）吻合，也解释了"只有进游戏才触发"。

**触摸驱动 `goodix_ts.ko` 不由本仓库编译**（来自 `vendor_dlkm`），所以内核侧改不到它。

## 本仓库做的改动

`scripts/ksu_fixes/10_ksu_input_hook_early_retire.sh` —— 消除内核在输入热路径上的
唯一差异（SUSFS 钩子）并修掉两个真实缺陷：

1. 钩子在**自旋锁（原子上下文）**里调 `pr_info()` → 已移除；
2. 钩子默认 `DEFINE_STATIC_KEY_TRUE`（开着），退休只依赖 `on_post_fs_data()` 单入口
   → 让 `ksu_is_safe_mode()` 也退休（用户态更早就会问），并在阈值达到后置"待退休"标志，
   由非原子入口消费（不能在原子上下文调 `static_branch_disable`，见 ReSukiSU #363）。

> ⚠️ **这不是已验证的修复。** 上述两个缺陷虽真实，但按现有证据**不足以解释**用户症状
> （钩子在 zygote 启动时就退休了，远早于任何游戏）。本改动的定位是**降低变量**。

## 定案所需的真机判据

```bash
# 1) 进游戏前后对比 game_mode_node 是否翻转 —— 决定性判据
P=$(adb shell "find /sys -name game_mode_node 2>/dev/null | head -1" | tr -d '\r')
adb shell "cat $P"      # 进游戏前后各读一次

# 2) 看驱动往触摸 IC 烧了哪些配置块（驱动会打印 try send config, id=0x%x）
adb shell "dmesg | grep -iE 'try send config|Game_.*_buff|_screen_.*_buff|game_mode (en|dis)able'"

# 3) 看配置块是否写失败（写失败 ⇒ 与触摸 IC 固件不匹配）
adb shell "dmesg | grep -iE 'failed write command' | sort | uniq -c"

# 4) 看手势是否在上报
adb shell "dmesg | grep -iE 'MZ_GESTURE|Report gesture|gesture_mask'"
```

判读：出现 `Game_*_screen_*_buff` → 游戏模式确实改写了边缘配置；
出现 `failed write command ..._buff` → 配置块与 IC 固件不匹配（更值得优先修）；
都没有 → 转向用户态输入栈。
