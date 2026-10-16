# 触摸问题诊断报告 — MEIZU21GKI run 23（meizu21-sukisu-23）

> 日期：2026-10-09 · 对象：`FengFaQ/MEIZU21GKI` release **`meizu21-sukisu-23`**（= 用户所说"润23"）
> 症状（用户原话）：**"就打游戏的时候会触发类似鼠标双击和长按。"**
> 结论：**不是 run 23 引入的、也不是内核 KMI/CFI 层的问题。**

---

## 0. 结论先行

| 判定 | 结论 | 证据强度 |
|---|---|---|
| run 23 是否改动了内核？ | ❌ **没有**。run 22 与 run 23 的内核二进制**完全等价** | ★★★ 提交级 diff |
| CRC（KMI 符号版本）层是否健康？ | ✅ **完全健康**。4891 个设备符号 **0 个 CRC 不匹配、0 个无法解析** | ★★★ 全量核对 |
| KCFI（CFI 类型哈希）层是否健康？ | ✅ **与原厂（可正常工作）内核等价** | ★★★ 对照组实验 |
| 触摸驱动能否正常加载？ | ✅ `goodix_ts.ko` 全部 142 个内核符号 CRC **逐个精确匹配** | ★★★ 逐符号核对 |
| 症状是否属于"崩溃"类？ | ❌ 不是。CFI 失配必然 `panic` + 看门狗重启，**不会**表现为"双击/长按" | ★★★ 机制推导 |
| 是否存在"把触摸翻译成双击"的通路？ | ✅ **已反汇编证实**：`mz_gesture_report` 手势分发器与 22 处 `input_event` 同在 `goodix_ts_threadirq_func` 里 | ★★★ 反汇编实证 |
| 是否有"边缘分区"配置能改判读？ | ✅ **已证实**：驱动向触摸 IC 烧 `Game_*_screen_*_buff` / `Horizontal_screen_left/right_buff` 等 **21 个固件配置块** | ★★★ 字符串表实证 |
| 触摸固件在 DSU 下是否可用？ | ✅ **可用**：`/vendor/firmware/goodix_*.bin` 实测存在于原厂 vendor；两条路线（DSU / 只换内核）都不动 vendor | ★★★ sparse/erofs 实测 |
| 触摸模块依赖/加载顺序是否有问题？ | ❌ **无问题**：依赖闭包 6 个模块、缺失 0；`modules.load` 顺序本非权威（libmodprobe 按 `modules.dep` 拓扑排序） | ★★★ 实测排除 |
| 是不是 SUSFS / KSU 干扰了输入？ | ❌ **已实证排除**：SUSFS 确实 hook 了 `input_handle_event`，但实现只读 `KEY_VOLUMEDOWN` 计数、**从不改写** type/code/value，且开机 `post-fs-data` 即关闭 | ★★★ 源码级实证 |
| run 23 是换系统还是只换内核？ | ✅ **只换内核**（`anykernel.sh`: `do.modules=0`/`block=boot`），**系统仍是原厂 Flyme** | ★★★ AK3+boot头实测 |
| Flyme 是否有"游戏模式"写入方？ | ✅ **实测存在**：Flyme 内含 `game_mode_node` 路径模板、`game_mode_intervention.list`、PUBG 配置 | ★★★ super.img 实测 |
| 真正的问题域 | ⚠️ **触摸驱动 `game_mode` / 手势 / 边缘分区配置 + Flyme 用户态写入方**，非内核 | ★★★ 反汇编 + 字符串实证 |

### 五轮排查的收敛轨迹

| 轮次 | 得到什么 | 排除/收窄了什么 |
|---|---|---|
| 1 | 内核无罪（KMI/CFI 逐项等价） | 排除 KMI 失配、CFI 失配、run23 回归 |
| 2 | 手势分发器与触摸上报同处 IRQ 处理函数 | 证实"一次触摸→手势"机制存在 |
| 3 | 驱动向触摸 IC 烧 **21 个具名配置块**（含边缘分区） | 找到唯一同时解释"双击 + 长按"的一层 |
| 4 | 固件存在、依赖完整、SUSFS 只读 | 排除固件缺失、模块加载顺序、KSU/SUSFS 干扰 |
| 5 | **路线修正**：run23 只换内核、Flyme 完整保留；实测 Flyme 里确有 `game_mode_node` 写入方 | 推翻"用户态组件不存在"的旧前提；补上"为何只有游戏触发"的解释 |

**一句话**：刷 run 23 出现"游戏里像双击/长按"，**不是内核 KMI/CFI 层面的故障**（那会导致 panic + 重启，而非手感异常）。
现象与 **Flyme 游戏模式改写触摸 IC 的边缘/报点配置** 这条路经高度吻合，
而该路经**只在进游戏时被 Flyme 用户态触发** —— 与"只有打游戏才出现"逐字对应。
**最终确认仍需一次真机日志（§7）。**

---

## 1. "润23"是什么

用户说的"润23"= 仓库 release 标签 **`meizu21-sukisu-23`**：

| 项 | 值 |
|---|---|
| tag | `meizu21-sukisu-23` |
| run number / id | **#23** / `37096230203` |
| 构建提交 | `cd9372ac` |
| run 页面 | https://github.com/FengFaQ/MEIZU21GKI/actions/runs/37096230203 |
| 结果 | success |
| 变体 | ReSukiSU / SUSFS=true / LTO=none |
| 产物 | `android14-6.1.25-2023-10-boot.img`（100,663,296 B）、AnyKernel3、管理器 APK |

> 说明：`refs/tags/meizu21-sukisu-21/22/23` 都指向最新构建（release 只保留最近 3 版），
> `meizu21-latest` 是稳定入口。**"润"= run 的音译**。

---

## 2. 关键事实：run 23 的内核 == run 22 的内核

`cd9372a`（run 23 编译的提交）相对 `6f4a6e0`（run 22 编译的提交）的改动：

```
 .github/workflows/build.yml |  45 +++++++++-------
 tools/kcfi_expect.py        | 123 ++++++++++++++++++++++++++++++++++++++++++++
 tools/verify_meizu21gki.py  |  12 ++++-
 3 files changed, 160 insertions(+), 20 deletions(-)
```

- `tools/kcfi_expect.py` —— **新增的离线分析工具**，不参与编译。
- `tools/verify_meizu21gki.py` —— 仓库自检脚本，不参与编译。
- `build.yml` 的 45 行改动**全部在「CFI 类型哈希核对」这个 `if: always()` 的校验步骤里**：
  把原来对 `shrink_slab` 断言具体值、对 `mem_cgroup_id_remove` 只查"有无哈希"，
  改成对 6 个符号**逐项断言具体值**（`for pair in sym:hash` 循环）。

**即：run 23 只是把 CI 的断言收紧，产出的 boot.img 与 run 22 是同一个内核。**

推论：如果用户"换了 run 23 才出问题"，那么这个"换版本"不是原因 ——
要么是 22 也有同样现象（只是没注意），要么变量在别处（管理器版本 / 刷入方式 / 用户态）。

> ⚠️ 附带提醒：run 22 引入的 **ReSukiSU 改为每次现场从 GitHub 拉最新**（`KSU_REF` 默认 `main`）
> 是一个**真实的、随上游漂移的变量**。同一 tag 名下的管理器 APK 会变。这是本项目当前
> 唯一"每次构建可能不同"的输入，怀疑触摸问题时值得一并锁定（见 §6）。

---

## 3. 证据一：KMI（CRC）层完全健康

设备 472 个厂商模块共 **4891 个**"需要内核提供"的符号。用 run 23 实际产物
（`dist` 分支的 `Module.symvers.patched`）逐条核对：

```
NEED=4891   not_in_kernel=1414   not_in_any_module_either=0
MATCH=3477   CRC-MISMATCH=0      MISSING=0(真正的)
```

- **CRC 不匹配 = 0** —— 补丁机制（`tools/patch_kcrctab.py` 改写 88 个符号的 CRC）工作正常。
- 1414 个"不在内核里"的符号，**全部**由其它厂商模块 `DEF` 提供（module-to-module 依赖），
  这是正常且必要的结构；**没有任何一个符号无法解析**。

**触摸/输入栈专项**（逐个 `__versions` 比对，0 失配）：

| 模块 | `__versions` 条目 | CRC 匹配 | 失配 |
|---|---|---|---|
| `goodix_ts.ko`（触摸主驱动） | 161 | **142** | **0** |
| `mz_gesture_ts.ko`（手势/FOD） | 15 | 13 | 0 |
| `cs_press_f71.ko` / `cs_press_m68.ko` | 68 / 84 | 67 / 79 | 0 |
| `pm8941-pwrkey.ko` | 27 | 27 | 0 |
| `msm_drm.ko`（显示） | 740 | 624 | 0 |
| `haptic_aac.ko` / `qcom-hv-haptics.ko`（振动） | 80 / 124 | 79 / 122 | 0 |

`goodix_ts.ko` 需要的 19 个"内核里没有"的符号（`mz_gesture_report`、`Gesture_switch_enable`、
`FOD_switch_enable`、`panel_event_notifier_register` 等）已确认**全部由其它厂商模块导出**，
不是缺失。

---

## 4. 证据二：KCFI（CFI 类型哈希）层与原厂等价

这是本项目历史上真正踩过的坑（`shrink_slab` 缺失哈希 → 开机 90 秒 CFI panic → 看门狗重启）。
本次做了**对照组实验**，方法如下：

1. 从**原厂** `boot.img`（Flyme 12.6 线刷包）解出内核 Image（33,892,864 B，`6.1.25-android14-11-maybe-dirty`）。
2. 从 **run 23 产物** `dist` 分支的 `boot.img` 解出内核 Image（34,822,656 B，同版本串）。
3. 扫 `goodix_ts.ko` 的 `.text`，按 `brk #0x8228`（`0xd4304500`）+ `movz/movk` 常量序列
   抽出它在**每个间接调用点写死的期望哈希** → **18 个不同哈希 / 257 个调用点**。
4. 在两个内核里各自统计这 18 个哈希作为"函数入口前 4 字节"出现的次数。

结果：

| | 我们的内核（run 23） | 原厂内核（对照） |
|---|---|---|
| 18 个哈希中在内核里出现 | **4** | **4** |
| 具体命中 | `851588c7`(2), `89fb613d`(122), `8f79e0b0`(1), `e01408cd`(126) | 同 4 个 (2/91/1/123) |

**两个内核完全一致。** 那 14 个"没在内核里"的哈希是**模块内部函数**的类型哈希
（模块自己 `.text` 里就带着），根本不该出现在内核里 —— 这也正是仓库 `kcfi_expect.py`
注释里警告过的"别用字面搜索当判据"。

对全栈做同样的统计，结论一致（越靠右越说明我们**不比原厂差**）：

| 模块 | 期望哈希 | 我们命中 | 原厂命中 |
|---|---|---|---|
| `goodix_ts.ko` | 18 | 4 | 4 |
| `msm_drm.ko` | 505 | **42** | 41 |
| `i2c-msm-geni.ko` | 8 | 4 | 4 |
| `spi-msm-geni.ko` | 5 | 2 | 2 |
| `haptic_aac.ko` | 9 | 1 | 1 |
| `qcom-hv-haptics.ko` | 4 | 0 | 0 |
| `cs_press_f71.ko` / `vl53l1.ko` / `pinctrl-msm.ko` | 1 / 1 / 1 | 1 / 1 / 1 | 1 / 1 / 1 |

CI 钉住的 6 个哈希在 run 23 内核里**全部存在**（`shrink_slab` 1 处、`find_lock_task_mm` 1 处、
`mem_cgroup_id_remove` 11 处、`sched_show_task` 89 处、`setup_per_zone_wmarks` 1360 处；
`android_debug_symbol` 两边都无"入口形态"，见下）：

> `android_debug_symbol` 在两边的"入口前 paciasp"形态都是 0 处 —— 说明它并非以标准
> 函数入口被间接调用（可能是取地址做比较/打印而非调用）。**原厂同样如此**，故非风险。

---

## 5. 为什么"双击/长按"不可能是 CFI 问题

这是机制层面的排除，不依赖上面的统计：

KCFI 失配的后果是**确定的、灾难性的**，不可能退化成"手感异常"：

```
ldr  w16,[x8,#-4]      ; 取被调函数入口前 4 字节 = 内核的类型哈希
movz/movk w17,#hash    ; 模块编译期写死的期望值
cmp  w16,w17
b.eq +8
brk  #0x8228           ; ← 不匹配就走这里
blr  x8
```

`brk #0x8228` 触发 `CFI failure` → `Kernel panic - not syncing: Oops - CFI: Fatal exception`
→ 看门狗复位。**表现是"卡死 2~3 秒后重启"**，不是"点一下变两下"。

用户描述的是**事件语义**问题（一次触摸被解释成双击 / 被解释成长按），
这在物理上只能来自：
1. 触摸驱动把**一个**触摸帧上报成了**多个** press/release 序列；
2. 或上报的时序被拉长，超过用户态的长按判定阈值；
3. 或用户态（GSI 的 InputReader / HAL）对同一事件的重复消费。

三者都在**驱动的事件上报逻辑 + 用户态输入栈**，与 KMI/CFI 无关。

---

## 6. 真正的嫌疑点（按优先级）

### 6.0 ★★★ 本轮重大认知修正：run 23 是"**只换内核**"，Flyme 系统侧**完整保留**

前几轮我按 `记忆/` 里的 **DSU 路线**推理，写成"换成 GSI 后写 `game_mode` 的用户态组件不存在"。
**这个前提对本问题是错的。** 本轮核实清楚：

| 路线 | 换什么 | 系统侧 | 对应产物 |
|---|---|---|---|
| A. GSI + DSU（`记忆/` 项目） | 只换 `system/system_ext/product` | uwuAOSP | `work/dsu/*.zip` |
| **B. GKI 内核（`gki/` + MEIZU21GKI）** | **只换 `boot` 分区内核** | **原厂 Flyme** | **run23 的 `boot.img` / AK3** |

run 23 产出的是 `android14-6.1.25-2023-10-boot.img` + `AnyKernel3.zip`，
其 `anykernel.sh` 明确写着：

```sh
do.modules=0        # 不替换任何内核模块
do.systemless=0
block=boot          # 只动 boot 分区
```

且实测 `boot.img` 头部与**原厂完全同构**（`os_version=0x1c00017a`、`header_version=4`、
`header_size=1584`、`ramdisk_size=0`），仅内核载荷不同。

→ **结论：run 23 场景下系统是原厂 Flyme，`/vendor`、`/vendor/firmware`、
Flyme 的触摸相关用户态服务全部在位。**

**而这正好让"游戏模式"这条线索从"可能"变成"很可能"** —— 因为：

**(a) Flyme 里确实存在写 `game_mode_node` 的用户态**（本轮实测，扫原厂 `super.img`）：

```
game_mode            出现 16 次
/data/system/game_mode_intervention.list          ← 游戏模式"干预"列表（按游戏包名生效）
game_mode_config / game_mode_only / game_mode_record
mz_game_mode_landscape_swipe_up_width_fraction    ← 横屏上滑宽度（防误触参数）
"...landscape...pubg..."                          ← 明确出现 PUBG 的游戏模式配置
res/mipmap-*/func_change_to_game_mode.png         ← 系统 UI 里有"切到游戏模式"图标
```

**(b) 存在指向触摸驱动的 sysfs 路径模板**（同一个 blob 内相邻字符串）：

```
.../meizu/main_tp          ← 魅族触摸主节点
fingerprint_stabilize
game_mode_node             ← ★ 直接写到触摸驱动的游戏模式节点
.../platform/.../goodix_ts.0/...
```

**这条链路现在完全闭合**：
Flyme 用户态（按游戏包名）→ 写 `game_mode_node` → 驱动
`goodix_ts_game_mode_store()` → 向触摸 IC 烧 `Game_*_screen_*_buff` 边缘配置
→ 触摸判读行为改变 → **一次按压被拆成多次 / 被保持** → 用户看到的"双击 + 长按"。

> **为什么"只有打游戏才触发"现在有了确切解释**：这个游戏模式是
> **按游戏包名、由 Flyme 在进游戏时主动写入**的。不在游戏里就不会被写，
> 所以日常使用完全正常 —— 与用户描述**逐字吻合**。

---

### 6.1 ★★★ 触摸驱动的 `game_mode` / 手势链路

`goodix_ts.ko` 内建了一整套**游戏模式与手势**逻辑，字符串实证：

```
game_mode enable / game_mode disable
Game_Horizontal_screen_left_buff  / Game_Horizontal_screen_right_buff
Game_Vertical_screen_buff
Frame rate switch is 60hz / 120hz / 180hz / 240hz
```

对应的**用户态可控 sysfs 节点**（`dev_attr_*` 实证）：

| 节点 | 作用 |
|---|---|
| `game_mode_node` | 游戏模式开关（**直接改变触摸上报行为**） |
| `screen_game_mode_node` | 分横/竖屏的游戏模式 |
| `frame_rate_node` | 触摸报点率切换（60/120/180/240 Hz） |
| `gesture_control` | 手势掩码（`mz_gesture_ts.ko` 提供） |
| `gesture_info` / `gesture_buff` | 手势配置（写入触摸 IC） |
| `prevent_mistake_touch` | **防误触**开关 |
| `fod_report` | 指纹区（FOD）上报 |

#### 6.1.0 ★★★ 本轮关键发现：这套开关写的是**触摸 IC 的固件配置块**，其中含"边缘分区"

这是本轮从字符串表挖出的、之前遗漏的一层。驱动通过 `send_cfg_cmd` 把**具名配置缓冲**
烧进触摸控制器固件（失败会打印 `failed write command <名>_buff`）。全部配置块清单：

| 配置缓冲 | 含义 |
|---|---|
| `gesture_buff` | 手势配置 |
| `Game_Vertical_screen_buff` / `_close_buff` | 游戏模式：**竖屏**配置 |
| `Game_Horizontal_screen_left_buff` / `_close_buff` | 游戏模式：**横屏左区** |
| `Game_Horizontal_screen_right_buff` / `_close_buff` | 游戏模式：**横屏右区** |
| `Vertical_screen_buff` / `_close_buff` | 普通模式：竖屏 |
| `Horizontal_screen_left_buff` / `_close_buff` | 普通模式：**边缘左区** |
| `Horizontal_screen_right_buff` / `_close_buff` | 普通模式：**边缘右区** |
| `FOD_enable_buff` / `FOD_disable_buff` | 指纹区使能 |
| `fp_enable_buff` / `fp_disable_buff` | 指纹使能 |
| `usb_charge_enable_buff` / `_disable_buff` | USB 充电场景 |
| `wireless_charge_enable_buff` / `_disable_buff` | 无线充电场景 |
| `sleep_cmd` | 休眠 |

**为什么这一层对"双击/长按"特别重要**：
`Horizontal_screen_left/right_buff` 这类**边缘分区（edge region）配置**，
决定的正是"屏幕边缘那一条区域的触摸如何被判读"。边缘配置错配时的典型表现就是
**一次触摸被拆成多次上报、或被保持不放** —— 也就是用户描述的
"类似鼠标双击和长按"。而游戏场景恰恰最容易触发边缘区域
（横屏握持、虚拟按键贴边、多指同按）。

**这条链路正好解释用户症状**（已按 §6.0 的路线修正重写）：
- 游戏模式会改变**报点率**与**边缘分区配置**（`Game_*_screen_*_buff`，写入触摸 IC）；
- **Flyme 用户态按游戏包名主动写入**（§6.0 已实测：Flyme 里有 `game_mode_node`
  路径模板、`game_mode_intervention.list`、连 PUBG 的配置都有）；
- 进游戏时它写 `game_mode_node=1` → 驱动把**游戏模式的边缘/报点配置烧进触摸 IC**
  → 触摸判读行为改变 → **同一物理按压被拆成多次上报 → 表现为双击/长按**；
- 退出游戏写回 0 → 恢复正常。**这解释了"只有打游戏才触发"**。

> **为什么这会因为"换内核"而暴露出来**：Flyme 的游戏模式原本是
> **与原厂内核配套调校**的（同一份 `goodix_cfg_group.bin` + 同一版驱动逻辑）。
> 换成 GKI 内核后，触摸驱动的编译产物变了，其行为可能与 Flyme 用户态的预期
> 不完全一致。但这**只是众多可能之一**，必须靠 §7 的实测区分。

#### 6.1.1 ★★★ 反汇编实证：手势分发器 `mz_gesture_report`（本轮新增，已推翻"纯推测"）

这一步把 §6.1 从"合理推测"升级为**已证实的机制**。反汇编 `goodix_ts.ko` 与
`mz_gesture_ts.ko`（自研轻量 AArch64 反汇编器 `a64dis.py`）得到：

**(a) 触摸上报主路径确实调用手势分发器**

> ⚠️ 方法学修正（本轮）：`.rela.text` 的 `r_offset` 是 **`.text` 节内相对偏移**，
> 文件偏移应为 `r_offset + .text节偏移(0x3670)`。第一版报告里按 `-0x3670` 换算，
> 导致调用点归属**错位了一个函数**。下表是修正后的**准确**归属
> （判据：只统计 `R_AARCH64_CALL26 = 283` 的真·直接调用，与 `.text` 里 1691 个
> `0x94000000` 未重定位占位符数量**完全吻合**，可交叉验证）。

`goodix_ts.ko` 里对关键符号的**直接调用**归属：

| 被调用符号 | 所在函数 | 调用点数 |
|---|---|---|
| `input_event` | **`goodix_ts_threadirq_func`**（★ 触摸中断处理主函数） | **22** |
| `input_event` | `goodix_ts_release_connects`（释放全部触点） | 12 |
| `input_mt_sync_frame` | `goodix_ts_release_connects` | 1 |
| **`mz_gesture_report`** | **`goodix_ts_threadirq_func`** | **2** |
| `mz_gesture_report` | `gsx_gesture_ist` | 3 |
| `mz_gesture_report` | `goodix_fod_state_work` | 1 |
| `mz_gesture_report` | `__goodix_ts_suspend` | 1 |
| `goodix_gesture_function` | `goodix_sleep_store` / `__goodix_ts_suspend` / `goodix_ts_gesture_store` | 2/2/1 |

**结论**：`goodix_ts_threadirq_func` 是触摸中断处理主函数，它同时做两件事 ——
**上报 22 处 `input_event`（触摸事件）**，以及**调用 2 次 `mz_gesture_report`（手势分发）**。
两者在**同一个中断处理函数里**，这就是"一次触摸既被当普通触摸上报、又被当手势解释"
的结构性来源。

**(a2) 中断处理函数里 `mz_gesture_report` 的实参（反汇编实证）**

```
0x00d430:  movz w2, #0x829          ; （前一个调用）
0x00d434:  bl   ...
0x00d438:  mov  w0, w23             ; arg0 = 设备上下文
0x00d43c:  movz w1, #0x272          ; ★ arg1 = 手势 event code = 0x272
0x00d440:  movz w2, #0x1            ; arg2 = 1
0x00d444:  movz w24, #0x1
0x00d448:  bl   mz_gesture_report   ; ★ 手势分发
0x00d44c:  mov  w0, w23
0x00d450:  mov  w1, wzr
0x00d454:  mov  w2, wzr
0x00d458:  mov  w3, wzr
0x00d45c:  bl   ...                 ; （复位/清理）
```

第二处调用点（file 0xd864）同理是 `movz w1, #0x272` + `movz w2, #0`（参数不同，见 §6.1.2）。

查 §6.1.1(c) 的分发表：**`0x272` → gesture id 25**。
也就是说 IRQ 处理函数会以 `code=0x272`（映射到 gesture 25）调用手势分发器。

**(b) `goodix_ts_game_mode_store` 的反汇编（372 B）**

```
...
0x00eea4:  movk w17, #0x7c6f
0x00eea8:  movk w17, #0x493f0000, lsl #16    ; w17 = 0x493f7c6f
0x00eeac:  cmp  w16, w17
0x00eeb0:  b.eq 0xeeb8
0x00eeb4:  brk  #0x8228                       ; KCFI 校验
0x00eeb8:  blr  x8
...
.rela.text: off=0x00ef18 (CALL26)  sym=mz_gesture_report   ← ★ 直接调用
```

即：**写 `game_mode_node` → 直接调用 `mz_gesture_report`**。开关与手势上报是硬连线的。

> 附注：该函数里 `blr x8` 前的 KCFI 期望哈希是 **`0x493f7c6f`**，
> 实测**两个内核里都不存在**该哈希字面量 —— 说明 `x8` 指向的是
> **模块内部函数**（其哈希在模块自己的 `.text` 里），不是内核函数。这与
> §4 的"模块内部哈希不该出现在内核"判断一致。

**(c) `mz_gesture_report` 本体（`mz_gesture_ts.ko`，744 B）是一个手势分发器**

```
0x0012bc:  sub  w9, w19, #0x270     ; w19 = 传入的 event code
0x0012c0:  cmp  w9, #0x2a           ; 合法区间 0x270..0x29a
0x0012c4:  b.hi 0x12fc              ; 越界 → 告警并丢弃
0x0012c8:  adrp x10, ...            ; 分发表基址
0x0012d0:  mov  w8, wzr
0x0012d4:  adr  x11, 0x12e4         ; 跳转表基址
0x0012d8:  ldrb w12, [x10, x9]      ; 查表取分支偏移
0x0012dc:  add  x11, x11, x12
0x0012e0:  br   x11                 ; 跳转分发
0x0012e4:  movz w8, #0x4            ; → gesture 4
0x0012ec:  movz w8, #0x5
0x0012f4:  movz w8, #0x6
... （后续分支 movz w8, #1..#14）
```

配套的 `.rodata` 分发表（已解码）：

| event code | gesture id |
|---|---|
| `0x280` | 1 |
| `0x281` | 2 |
| `0x282` | 3 |
| `0x283` | 4 |
| `0x270` | 5 |
| `0x271` | 6 |
| **`0x272`** | **25** ← IRQ 处理函数传的就是这个 |
| `0x290` | 8 |
| `0x291` | 9 |

**(d) 驱动自己就把手势命名为 DOUBLE-TAP / SINGLE-TAP**

`goodix_ts.ko` 的 `.rodata.str1.1` 里有：

```
get DOUBLE-TAP gesture          ← ★ 与用户描述逐字对应
get SINGLE-TAP gesture
get SWIPE-UP / DOWN / LEFT / RIGHT gesture
get FOD-DOWN / FOD-UP gesture
get GESTURE_C gesture
```

**(e) 手势受一个用户态可写的掩码控制**

`mz_gesture_ts.ko` 字符串：

```
gesture_control                              ← sysfs 节点名
mz_sysfs_gesture_control_store
"all gestures have disabled, ignore this gesture 0x%x."
"Ignore gesture 0x%x [mask:0x%08x]"
"gesture_button = %02x ,FOD_switch_enable = %x ,Gesture_switch_enable = %x"
"Report gesture 0x%x [mask:0x%08x, pos:%d]"
"tp"                                          ← 绑定的输入设备名 = 触摸屏
```

**结论**：从"写 sysfs 开关"到"上报 DOUBLE-TAP 手势"是一条**完整、可反汇编验证的通路**，
而且**手势分发器与触摸事件上报位于同一个中断处理函数 `goodix_ts_threadirq_func` 里**
（该函数含 22 处 `input_event` + 2 处 `mz_gesture_report`）。
这解释了为什么症状表现为"一次触摸被识别成双击"——**驱动确实有一个把事件翻译成
DOUBLE-TAP/SINGLE-TAP 的分发器，它与普通触摸上报同处一个 IRQ 处理流程，而它的掩码由用户态控制**。

> ⚠️ 重要的边界：以上证明的是**机制存在且可被触发**，尚未证明用户手上那台机器
> **确实**被写成了非默认值。**第 6.1 节的 sysfs 读取仍是必要的一步实测**——
> 它只需要 5 分钟，却能直接坐实或排除本假设。请务必先做那一步。
>
> 另需说明：本报告**没有**证明"是内核算错导致重复上报"。IRQ 处理函数里 22 处
> `input_event` 是**多点触控协议的正常形态**（每个 slot 的 `ABS_MT_*` 都要单独
> `input_event` 一次，驱动为性能把它展开成直线代码），本身不等于 bug。
> 真正的判据仍是真机实测（§7）。

**首要排查动作**（真机，root）：

> ★ 由于 §6.0 已确认"系统是原厂 Flyme、写入方存在"，**下面第 5 步是本报告最关键的判据**。

```bash
# 1) 定位触摸驱动的 sysfs 根（含新发现的 gesture_control / prevent_mistake_touch）
adb shell "find /sys -name 'game_mode_node' -o -name 'frame_rate_node' \
  -o -name 'screen_game_mode_node' -o -name 'gesture_control' \
  -o -name 'gesture_info' -o -name 'prevent_mistake_touch' 2>/dev/null"

# 2) 读当前状态（看是否被置成非默认值）
adb shell "for f in game_mode_node screen_game_mode_node frame_rate_node \
  gesture_control gesture_info prevent_mistake_touch; do \
  p=\$(find /sys -name \$f 2>/dev/null | head -1); \
  [ -n \"\$p\" ] && echo \"\$p = \$(cat \$p 2>/dev/null)\"; done"

# 3) 看手势是否在"被上报"（这是双击症状的直接证据）
adb shell "dmesg | grep -iE 'MZ_GESTURE|Report gesture|Ignore gesture|all gestures have disabled'"

# 4) 进游戏前后各读一次第 2 步，对比哪个节点被改了 → 那就是"元凶写入方"

# 5) ★★★ 决定性判据：实时抓"谁在游戏里写 game_mode"
#    法一：持续轮询节点值，看它是否在进游戏瞬间从 0 变 1
adb shell "P=\$(find /sys -name 'game_mode_node' 2>/dev/null | head -1); \
  echo \"node=\$P\"; \
  for i in \$(seq 1 300); do echo \"\$(date +%s) \$(cat \$P 2>/dev/null)\"; sleep 1; done" > gm_trace.txt
#    然后启动游戏，观察 gm_trace.txt 里值何时翻转
#
#    法二（更直接）：打开触摸驱动调试日志，看进游戏时驱动打印了什么
adb shell "echo 1 > /proc/sys/kernel/printk; dmesg -C"
#    启动游戏，等 5 秒后：
adb shell "dmesg | grep -iE 'GTP-(INF|DBG)|MZ_GESTURE' | head -60"
```
若发现 `game_mode=1` 或手势掩码被打开，先关掉再复测：
```bash
for n in game_mode_node screen_game_mode_node prevent_mistake_touch; do
  p=$(adb shell "find /sys -name '$n' 2>/dev/null | head -1" | tr -d '\r')
  [ -n "$p" ] && adb shell "echo 0 > $p"
done
# 手势掩码：gesture_control 写 0 = 全关（驱动日志会打印 "all gestures have disabled"）
p=$(adb shell "find /sys -name 'gesture_control' 2>/dev/null | head -1" | tr -d '\r')
[ -n "$p" ] && adb shell "echo 0 > $p"
adb shell "dmesg | tail -30"      # 应能看到 mz_gs.gesture_mask1/2 = 0x0
```

> 判据很干脆：**关掉手势掩码后游戏内双击/长按消失 ⇒ 就是这条链路**。
> 若关掉后症状不变，则回到 §6.2（固件/配置组）与 §6.4（用户态输入栈）。

**新增（本轮）：直接看"边缘/游戏配置块"是否被烧进触摸 IC**

驱动每写一个配置块都会打印一行 `try send config, id=0x%x`；失败则打印
`failed write command <名>_buff`。所以这一条日志就能定案：

```bash
# ① 看进了游戏之后，驱动往触摸 IC 烧了哪些配置块
adb shell "dmesg | grep -iE 'try send config|Game_.*_buff|_screen_.*_buff|game_mode (en|dis)able'"

# ② 看游戏模式/边缘配置是否被写失败（写失败 ⇒ 配置与固件不匹配）
adb shell "dmesg | grep -iE 'failed write command' | sort | uniq -c"
```

判读：
- 出现 **`Game_Horizontal_screen_left/right_buff`** 或 **`Horizontal_screen_right/left_buff`**
  → 游戏模式**确实改写了边缘分区配置**，与症状高度吻合；
- 出现 **`failed write command ..._buff`** → 配置块与触摸 IC 固件**不匹配**
  （多半是 `goodix_cfg_group.bin` 版本问题），这条更值得优先修；
- 两条都没有 → 症状更可能来自 §6.3（KSU/SUSFS）或 §6.4（用户态输入栈）。

### 6.2 ★★☆ 触摸固件/配置组与 `goodix,brl-d-m2461`

驱动 DT 匹配表里**明确支持魅族21**：

```
goodix,brl-a / goodix,brl-b / goodix,brl-d / goodix,nottingham
goodix,brl-d-evb / goodix,brl-d-m2461   ← M2461 = 魅族21
goodix,brl-d-m2481
```

固件走 `request_firmware` 加载 **`goodix_firmware.bin`** + **`goodix_cfg_group.bin`**
（DTS 里 `goodix,firmware-name` / `goodix,config-name` 指定）。

**风险**：这属于 **vendor 侧资产**。DSU/GSI 路线下，若这些文件所在的分区
（`/vendor/firmware/` 或 `odm`）与内核期望不一致，驱动会走到
`Firmware image [%s] not available` / `use default` 分支 → **用默认配置运行** →
手感/报点行为与原厂不同。这正是"只有玩游戏才明显"的典型来源
（游戏对报点率和多点时序最敏感）。

#### 6.2.1 本轮实测：固件**确实存在**，且在两条路线下**都不会被替换**

这一项本轮已用实证收窄，**风险等级从 ★★☆ 下调为 ★☆☆（仅剩"版本/内容是否一致"的残余疑问）**：

**(a) 原厂固件文件实测存在**（扫 `super.img` 的 sparse 块，1 次精确命中）：

```
goodix_cfg_group.bin        ← 触摸配置组（含边缘 / 游戏模式配置）
goodix_cfg_group_evb.bin
goodix_firmware.bin         ← 触摸固件本体
goodix_firmware_evb.bin
haptic_config.bin           ← 振动配置（同一目录）
```

**(b) 它们所在的分区已确认**：该文件名列表位于一个 **erofs** 文件系统内
（魔数 `0xe0f5e1e2`、`blkszbits=12`、`blocks=375983` → 1,540,026,368 B ≈ 1.43 GiB），
与 `vendor` 分区的尺寸量级吻合 → 即 **`/vendor/firmware/`**。

**(c) DSU/GSI 路线不替换 vendor**：底包 `vendor_boot` 里的权威 `fstab.qcom` 实测：

```
vendor  /vendor  erofs  ro  wait,slotselect,avb=vbmeta,logical,first_stage_mount
odm     /odm     erofs  ro  wait,slotselect,avb=vbmeta,logical,first_stage_mount
```

磁盘上的 `vendor` 来自**设备自己的 Flyme 分区**，而 DSU 包只含
`system / system_ext / product`（已核实 `uwuAOSP-meizu21-DSU-B.zip` 结构）。
→ **`/vendor/firmware/goodix_*.bin` 在运行时是可用且未被 GSI 覆盖的。**

**残余风险**：`goodix_cfg_group.bin` 里的**游戏模式/边缘配置块**是否与驱动的
期望版本匹配（驱动会做 checksum 校验）。若内容不符，驱动会走
`Bad firmware, cheksum error` / `use default` 分支 → 用默认配置运行。

排查（现在只需看日志，不必再找文件）：
```bash
adb shell "dmesg | grep -iE 'GTP-(INF|ERR).*(Firmware|cfg|checksum|default)'"
adb shell "ls -l /vendor/firmware/ | grep -i goodix"     # 应见 4 个 goodix_* 文件
```

### 6.2.2 ★★★ 本轮新排除：`goodix_ts.ko` 的模块依赖与加载顺序**没有问题**

之前担心"触摸模块加载不全 / 顺序错"会导致驱动半残。本轮实测**排除**：

**(a) 依赖闭包完整**（读 `vendor_dlkm/modules.dep`）：

```
/vendor/lib/modules/goodix_ts.ko: gh_irq_lend.ko  mz_gesture_ts.ko  mz_chg_manager.ko
                                  gh_mem_notifier.ko  panel_event_notifier.ko
```

`goodix_ts.ko` 的**传递依赖闭包 = 6 个模块，缺失文件 = 0**。

**(b) "加载顺序倒挂"是假警报**：`modules.load` 里
`[424] goodix_ts.ko` 排在它的依赖 `[425] mz_gesture_ts.ko` **前面**，看起来是倒挂。
但实测 `modules.load` 的顺序**本来就不是权威**：

- vendor_ramdisk 的 `modules.load` 里就有 **401 处**"依赖排在后面"的情况
  （例：`clk-dummy.ko[11]` 依赖 `gdsc-regulator.ko[12]`、`crm.ko[24]`、`qcom_dma_heaps.ko[60]`…）
- Android 的 `libmodprobe` 按 **`modules.dep` 做拓扑排序**，不看列表顺序

→ 所以 `mz_gesture_ts.ko` 会在 `goodix_ts.ko` 之前被加载，**依赖能被正确满足**。
**这条不是问题。**

**(c) 两块 partition 里的 `goodix_ts.ko` 逐字节相同**：
`vendor_boot` ramdisk 与 `vendor_dlkm` 的副本 SHA256 前缀都是 `b307c54851d81b41`，同 392,360 B。

### 6.3 ★☆☆ ReSukiSU/SUSFS —— 本轮**已实证排除**（含对 input 子系统的直接检查）

> ⚠️ 这是本轮最有价值的排除之一。上一版把这条列为 ★★☆，现已降至 ★☆☆ 并给出机制级证据。

**怀疑的由来**：run 22 起 `build.yml` 每次编译都从 `ReSukiSU/ReSukiSU` 拉 `main`，
且 SUSFS 默认打开了 10 个特性，其中 `SUS_MOUNT` / `SUS_PATH` / `OPEN_REDIRECT`
会拦截**路径解析与挂载** —— 而 `request_firmware` 正是按**路径**加载
`goodix_cfg_group.bin`。理论上存在"SUSFS 拦路径 → 固件读不到 → 用默认配置"的通路。

**实测结论：不成立。** 理由分两层：

**(a) SUSFS 确实 hook 了 input 子系统，但只读不改**

`susfs4ksu/kernel_patches/50_add_susfs_in_gki-android14-6.1.patch` 的改动文件清单里
**确实有 `drivers/input/input.c`**，插入点是所有输入事件的总入口：

```c
void input_handle_event(struct input_dev *dev, unsigned int type, unsigned int code, int value)
{
    disposition = input_get_disposition(dev, type, code, &value);
#ifdef CONFIG_KSU_SUSFS
    if (static_branch_unlikely(&ksu_is_input_hook_enabled))
        ksu_handle_input_handle_event(&type, &code, &value);   // 传的是指针！
#endif
    ...
}
```

注意签名是 **`unsigned int *type, unsigned int *code, int *value`** —— 理论上**可以改写**
事件类型/码/值。这看起来非常可疑，必须看实现。实现
（`kernelsu/kernel/runtime/ksud_integration.c:794`）是：

```c
int ksu_handle_input_handle_event(unsigned int *type, unsigned int *code, int *value)
{
    if (ksu_input_hook_inactive())
        return 0;

    if (*type == EV_KEY && *code == KEY_VOLUMEDOWN) {   // ← 只关心音量下键
        int val = *value;
        pr_info("KEY_VOLUMEDOWN val: %d\n", val);
        if (val)
            volumedown_pressed_count += 1;              // ← 只计数
    }
    return 0;
}
```

**它只读 `*type` / `*code` / `*value`，从不写回。** 唯一副作用是累加一个计数器
（用于"连按 3 次音量下进安全模式"）。对触摸事件（`EV_ABS` / `EV_KEY:BTN_TOUCH`）
它连分支都不进。
→ **SUSFS 的 input hook 不可能改变触摸行为。**

**(b) 该 hook 在开机极早期就被关掉**

`ksu_stop_input_hook_runtime()` 在 **`post-fs-data`** 阶段调用
（`ksud_integration.c` 的 post-fs-data 处理器），远早于任何游戏启动。
所以即使逻辑有问题，运行时也早已 `static_branch_disable`。

**(c) 残余的 `KSU_REF=main` 漂移问题仍在**（但性质变了）

它仍是"同一版号、内容可能不同"的**可复现性**问题，值得钉 tag；
但目前**没有证据**表明它与触摸症状相关。建议仍按 §7 用 `meizu21-bisect` 跑 L0 做**最终确认**
（一次构建即可，成本低）。


而 release 只保留最近 3 版 —— 用户手里的 23 与将来重建的 23 可能不同。

排查/锁定：
- 到仓库 `Settings → Secrets and variables → Actions → Variables` 设 `KSU_REF=<tag>`，重建一个确定版本；
- 或者用 `meizu21-bisect` 工作流跑 **L0（禁用 KSU）**：若 L0 下触摸正常，
  方向就转向 KSU/SUSFS 与触摸驱动的交互（例如 SUSFS 的 `umount`/路径重定向
  干扰了 `request_firmware` 读取固件）。

> 这条思路值得优先做，因为它是 **L0/L1 二分**能一句话证伪或坐实的，
> 而且 `meizu21-bisect.yml` 已经现成。

### 6.4 ★☆☆ 用户态输入栈（GSI 固有）

`uwuAOSP` 是 A17 GSI 跑在 A16 vendor 上。触摸 HAL 与 InputReader 之间有版本跨度，
"一次触摸 → 双击"也可能是 HAL 侧 `input_event` 语义（`BTN_TOUCH`/`ABS_MT_*` 序列）
与新 InputReader 的期望不符。这部分是 **GSI 路线固有损耗**，与内核无关。

---

## 7. 建议的验证顺序（成本从低到高）

| # | 动作 | 判定 | 成本 |
|---|---|---|---|
| 1 | **刷回 run 22**（或 `meizu21-sukisu-21`）复测同一游戏 | 若同样症状 → 排除"run 23 引入"，回到 §6.1 | 一次刷机 |
| 2 | 真机读 §6.1 的 sysfs 节点（进游戏前后各一次） | 找出被写入的节点 | 5 分钟 |
| 3 | `dmesg \| grep GTP` 看固件/游戏模式日志 | 看是否走了 default 固件分支 | 2 分钟 |
| 4 | `meizu21-bisect` 跑 **L0（禁用 KSU，SUSFS 功能消失）** | 若 L0 正常 → 锁定 KSU/SUSFS；若仍异常 → 排除内核 | 一次构建+刷机 |
| 5 | 用原厂 `boot.img`（已有）跑一次 DSU | 若原厂内核也异常 → 彻底排除内核，转向用户态 | 一次刷机 |

> 第 5 项很有价值：**原厂内核 + 同一个 GSI** 如果也出现"双击/长按"，
> 就直接证明问题在 GSI 的用户态/触摸 HAL，本项目内核完全无责。

---

## 8. 本次核对用到的产物与命令（可复现）

产物均在 `C:\uwuaosp\work\gki-check\`：

| 文件 | 说明 |
|---|---|
| `main_wt/` | `MEIZU21GKI` 的 `main` worktree（提交 `4666089`） |
| `dist_wt/` | `dist` 分支 worktree = **run 23 实际产物**（`f5e771d`，run 37096230203） |
| `ourboot/kernel` | 从 run 23 `boot.img` 解出的内核 Image（34,822,656 B） |
| `stockboot/kernel` | 从原厂 `boot.img` 解出的内核 Image（33,892,864 B） |
| `kcfi_expect.py` | 通用工具：抽厂商模块在每个间接调用点写死的 KCFI 期望哈希 |
| `kcfi_coverage.py` | 通用工具：统计内核里是否存在这些哈希作为"函数入口类型哈希" |
| **`a64dis.py`** | **自研轻量 AArch64 反汇编器**（无需 objdump；本轮用它证实手势分发通路） |
| `goodix_expect_hashes.txt` | `goodix_ts.ko` 的 18 个期望哈希 |
| `rewritten_syms.txt` | 补丁改写的 88 个符号 CRC 清单 |

关键命令：
```powershell
# 取 run 23 产物（dist 分支）
git -C <repo> worktree add --detach dist_wt dist

# 解内核
magiskboot.exe unpack boot.img          # → kernel

# KCFI 期望哈希（通用，可对任意 .ko）
python kcfi_expect.py <module.ko>

# KCFI 覆盖度（我们 vs 原厂 对照）
python kcfi_coverage.py ourboot\kernel  goodix_expect_hashes.txt
python kcfi_coverage.py stockboot\kernel goodix_expect_hashes.txt

# 反汇编（本轮证实手势通路用的）
# ★ 关键换算：.rela.text 的 r_offset 是 .text 节内相对偏移，
#   文件偏移 = r_offset + .text 节偏移(本模块 0x3670)
python a64dis.py goodix_ts.ko 0xeea4 0x20            # game_mode_store 的 KCFI 校验点
python a64dis.py mz_gesture_ts.ko 0x123c 0x2e8       # mz_gesture_report 分发器
python a64dis.py goodix_ts.ko 0xd438 0x20            # IRQ 里调 mz_gesture_report 的实参

# 重定位 → 调用图（只认 R_AARCH64_CALL26 = 283 的真·直接调用）
python - <<'PY'
import struct
d = open('goodix_ts.ko','rb').read()
# .text@0x3670 ; .rela.text@0x2b988 ; .symtab@0x548a0 ; .strtab@0x5c038
rel, symtab, strt = 0x2b988, 0x548a0, 0x5c038
rella, symsz = struct.unpack_from('<Q', d, 0x28)[0], None
# 每条 Ela: r_offset(u64) r_info(u64: sym<<32|type) r_addend(i64)
# type 283 = CALL26 -> 该偏移处就是 bl 指令
# 交叉验证：.text 里 0x94000000 占位符数量 == CALL26 数量（本模块均为 1691）
PY
```

---

## 9. 给上游仓库的建议（防回归）

1. **把触摸栈纳入 CI CFI 断言**：现在只断言 6 个符号（消费者是 `mz_kshrink_slabd` /
   `mz_hang_dump` / `smartswap_zram`）。`goodix_ts.ko` 有 257 个调用点却零断言。
   建议至少把 `delayed_work_timer_fn`、`seq_read`、`seq_lseek`、`single_release`
   这 4 个**命名 typeid**（模块以 `SHN_ABS` 形式引用，值即哈希）加进断言表 ——
   它们是触摸/显示/振动的公共热路径。
   > 实测这 4 个在 run 23 内核里**完全匹配**（`91b4a83a` / `e866e2f4` / `e61887de` / `8f07ca55`），
   > 加断言即可防未来回归。

2. **固定 `KSU_REF`**：`main` 漂移使同一 release 名不可复现。建议默认钉 tag（如 `v4.2.0-rc3`），
   需要尝鲜时再显式改用 `main`。

3. **`module_compat.txt` 的 `RESULT: FAIL` 是误报**：报告把"由其它模块提供"的符号
   也算成"缺失/不一致"（88 项 CRC 已由补丁修好，但报告仍显示 FAIL）。
   建议报告里区分"内核须提供"与"模块间提供"，否则每次都被 FAIL 麻痹。
   > 本次已用 `Module.symvers.patched` 全量核对证明**实际 0 失配**。

4. `device/meizu21/System.map` 与 `Module.symvers` 是 **0 字节占位文件** ——
   建议要么补真实内容，要么从仓库删除，避免误用。
