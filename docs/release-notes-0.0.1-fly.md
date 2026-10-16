# 0.0.1-fly — MEIZU21GKI 第一个正式版

基于 **run 22**（`meizu21-sukisu-22` / commit `6f4a6e05`）的产物，作为本项目的首个
**正式版（非预览）**发布。

| 项 | 值 |
| --- | --- |
| 内核 | `6.1.25-android14-11-maybe-dirty`（GKI `android14-6.1.25-2023-10`） |
| 设备 | 魅族21 / SM8650 / Pineapple / M2461 |
| 变体 | ReSukiSU + SUSFS（LTO = none） |
| 源 run | #22 / `37095878851` / `6f4a6e0` |
| 结构 | boot header v4，`os_version=14.0.0`，`os_patch_level=2023-10`，216 MiB→96 MiB 填充 |

## 为什么把 run 22 定为 0.0.1-fly

run 22 与 run 23 的内核二进制**完全等价** —— 两次构建之间只差 CI 断言与两个
不参与编译的分析工具（已逐文件核对）。所以 run 22 是"当前可用内核"的一个干净基线，
适合作为首个正式版。

## 安装

两种方式任选其一（都**只替换 boot 分区内核**，不动系统）：

1. **AnyKernel3**（推荐）：在支持 AK3 的自定义 recovery 里刷
   `android14-6.1.25-2023-10-AnyKernel3.zip`
2. **fastboot**：
   ```
   fastboot flash boot android14-6.1.25-2023-10-boot.img
   ```
   （`.img` 已按原厂大小 96 MiB 零填充，与原厂 boot 同构）

配套的 ReSukiSU 管理器 APK 也在本 release 的资产里（arm64-v8a）。

## 已知问题

- **触控**：有用户反馈"打游戏时会触发类似鼠标双击和长按"。
  排查结论见仓库 [`docs/触控问题诊断报告-run23.md`](../blob/main/docs/触控问题诊断报告-run23.md)：
  - 已排除：KMI/CRC 失配、CFI 类型哈希、run22/23 回归、SUSFS 输入钩子、触摸固件缺失、
    触摸模块依赖顺序；
  - 当前最强线索在 **vendor 侧**：Flyme 的"游戏模式"按游戏包名写触摸驱动的
    `game_mode_node`，驱动据此把边缘分区配置烧进触摸 IC —— 而触摸驱动
    `goodix_ts.ko` 由 `vendor_dlkm` 提供，**不由本仓库编译**；
  - **本版本（run 22）不含任何触控相关改动**，请如实按此理解。

## 校验

`Meizu21GKI` 的 CI 在每次构建时会校验：

- 设备 4891 个 KMI 符号的**存在性与 CRC**（`module_compat.txt`）；
- 6 个关键函数的 **KCFI 内联类型哈希**（缺一个即 fail，避免刷了会 panic 的包）；
- boot.img 结构与原厂**逐字段比对**。

本 release 的资产中附带了 `module_compat.txt` / `cfi_typeids.txt` /
`patch_crc_report.txt` / `source_revision.txt`，可离线复核。

## 许可

内核与产物为 **GPL-2.0-only**；ReSukiSU 管理器 APK 为 GPL-3.0（上游）。
详见仓库 `CREDITS.md` 与 `LICENSE`。
