# 第三方项目与引用清单

本文件列出 MEIZU21GKI 构建、打包、运行所依赖或引用的全部上游项目，供发布时逐项署名。
所有版本号/提交号均取自本仓库内的溯源文件（`kernelsu/SOURCE.txt`、`susfs4ksu/SOURCE.txt`、
`device/meizu21/SOURCE.txt`）与 CI 产物 `release/run-*/source_revision.txt`，非凭记忆填写。

---

## 一、构建直接依赖（发布必须署名）

### 1. Android Common Kernel (ACK) —— 内核源码本体

- 仓库：https://android.googlesource.com/kernel/common
- manifest：https://android.googlesource.com/kernel/manifest
- 分支：`deprecated/android14-6.1-2023-10`（manifest 分支 `common-android14-6.1-2023-10`）
- **固定提交：`0d89215310919593150f0ef047f9fd9902e02bc7`**
  （`UPSTREAM: net: sched: sch_multiq: fix possible OOB write in multiq_tune()`，2024-06-03）
- 对应内核：`6.1.25` / KMI `android14-11` / 安全补丁 2023-10
- 用途：GKI 内核树本体。本项目在其之上打 KernelSU + SUSFS 补丁
- 许可证：GPL-2.0

> 说明：魅族 21 的原厂内核**闭源，无公开源码**。本项目的做法是"原厂 ABI 对齐"——
> 只保证 KMI 符号/CRC/CFI 类型哈希与原厂一致，让原厂 vendor 模块能正常加载，
> **不包含任何原厂内核代码**。

### 2. AOSP 构建工具链

| 项目 | 链接 | 用途 | 许可证 |
|---|---|---|---|
| kernel/prebuilts/build-tools | https://android.googlesource.com/kernel/prebuilts/build-tools | 提供 `avbtool` 与 `testkey_rsa2048.pem` | 见上游 |
| platform/system/tools/mkbootimg | https://android.googlesource.com/platform/system/tools/mkbootimg | `mkbootimg`，生成 boot header v4 镜像 | Apache-2.0 |

### 3. ReSukiSU —— root 方案（默认变体）

- 上游：https://github.com/ReSukiSU/ReSukiSU
- 本仓库内置快照的直接来源：https://github.com/FengFaQ/ReSukiSU-fork
  - 分支 `main`，**固定提交 `34210a4dec297cb48ce4bfa1c5ba50a2f7d22641`**（2026-10-02）
- 集成方式与其官方 `kernel/setup.sh` 一致：符号链接 `common/drivers/kernelsu` + `drivers/Makefile` + `drivers/Kconfig`
- 许可证：**待核实**。仓库内 `kernelsu/LICENSE` 实测为 **GPL-3.0**，但 `kernelsu/SOURCE.txt` 标注 `GPL-2.0`——
  发布前请以实际源码树为准统一（内核本体是 GPL-2.0-only，GPL-3.0 与之不兼容，这一项务必确认后再发布）

### 4. SUSFS —— root 隐藏方案

- 上游：https://gitlab.com/simonpunk/susfs4ksu （GitLab，作者 simonpunk）
- GitHub 备用源：https://github.com/ShirkNeko/susfs4ksu
- 分支：`gki-android14-6.1`，**固定提交 `24743360ea08d98f6ad72b856851abed8de5854f`**（2026-09-26）
- 用途：只取 `kernel_patches/`（`fs/`、`include/`、`KernelSU/`、
  `50_add_susfs_in_gki-android14-6.1.patch`）与 `ksu_susfs` 工具
- 许可证：同样**待核实**（仓库内 `susfs4ksu/LICENSE` 实测 GPL-3.0，`SOURCE.txt` 标注 GPL-2.0）

### 5. AnyKernel3 —— 可刷 zip 打包模板

- 使用来源：https://github.com/WildKernels/AnyKernel3 （分支 `gki-2.0`）
- 上游原始项目：https://github.com/osm0sis/AnyKernel3
- 用途：生成 `AnyKernel3.zip`（`fastboot flash boot` 之外的另一种刷入方式）
- 许可证：见上游仓库（发布 zip 时请随包保留其 LICENSE）

---

## 二、可选变体与补丁来源（在 workflow 中按条件克隆）

| 项目 | 链接 | 说明 |
|---|---|---|
| SukiSU-Ultra | https://github.com/SukiSU-Ultra/SukiSU-Ultra | `SukiSU` 变体经其官方 `kernel/setup.sh` 集成 |
| SukiSU-Ultra（fork） | https://github.com/FengFaQ/SukiSU-Ultra-fork | `SukiSU` 变体的固定分支来源 |
| SukiSU_patch | https://github.com/ShirkNeko/SukiSU_patch | 额外 patch 来源 |
| kernel_patches | https://github.com/WildKernels/kernel_patches | 额外 patch 来源 |
| GKI_KernelSU_SUSFS | https://github.com/zzh20188/GKI_KernelSU_SUSFS | 参考实现 |
| Action-Build | https://github.com/Numbersf/Action-Build | CI 工作流模板来源 |
| Re-Kernel | https://github.com/Sakion-Team/Re-Kernel | 参考实现 |
| Baseband-guard | https://github.com/vc-teahouse/Baseband-guard | 基带保护相关补丁 |
| Droidspaces-OSS | https://github.com/ravindu644/Droidspaces-OSS | 参考实现 |

---

## 三、本仓库内置源码文档中的引用（KernelSU 生态，仅供致谢）

以下项目出现在内置的 KernelSU 源码/文档（`kernelsu/docs/`）或 SUSFS 的模块脚本里，
**与本 GKI 内核的编译产物无直接代码关系**，按需列入致谢即可：

- KernelSU 官方 —— https://github.com/tiann/KernelSU
- rsuntk/KernelSU —— https://github.com/rsuntk/KernelSU
- 5ec1cff/KernelSU —— https://github.com/5ec1cff/KernelSU
- 5ec1cff/ddk —— https://github.com/5ec1cff/ddk
- bmax121/KernelPatch —— https://github.com/bmax121/KernelPatch
- topjohnwu/Magisk —— https://github.com/topjohnwu/Magisk
- backslashxx/bindhosts —— https://github.com/backslashxx/bindhosts
- osm0sis/PlayIntegrityFork —— https://github.com/osm0sis/PlayIntegrityFork
- Dominium-Apum/kernel_xiaomi_chime —— https://github.com/Dominium-Apum/kernel_xiaomi_chime
- brevent/genuine —— https://github.com/brevent/genuine
- m0nad/Diamorphine —— https://github.com/m0nad/Diamorphine
- tdlib/telegram-bot-api —— https://github.com/tdlib/telegram-bot-api
  （仅出现在内置 KernelSU 源码自己的 CI 配置里，与本项目无关）

---

## 四、本项目自身仓库

| 仓库 | 链接 |
|---|---|
| MEIZU21GKI（本仓库） | https://github.com/FengFaQ/MEIZU21GKI |
| ReSukiSU-fork | https://github.com/FengFaQ/ReSukiSU-fork |
| SukiSU-Ultra-fork | https://github.com/FengFaQ/SukiSU-Ultra-fork |

设备树快照（`device/meizu21/`）来源为本机 9008 全分区备份提取的本地构建，
提交 `a65878179fd69c8c5b7bddd5bc82d6ec5a86ea0b`，未推送至远端。
注意：GKI 内核构建本身不需要设备树（dtb 在 `dtbo`/`vendor_boot` 分区，AnyKernel3 不附 dtb）。

---

## 五、许可证范围（2026-10-03 已修正）

### 本项目

**GPL-2.0-only**，完整条款见仓库根目录的 [`LICENSE`](LICENSE)。

> 修正记录：本仓库根 `LICENSE` 原先是 KernelSU 上游 userspace 那份 GPL-3.0 的副本
> （实测与 `kernelsu/LICENSE` 的 SHA256 完全相同）。但本项目产出的是 **GPL-2.0 的 Linux 内核二进制**，
> 用 GPL-3.0 声明既不符合本项目自身条件，也与产物不一致，且 GPL-3.0 与 GPL-2.0-only 并不兼容。
> 现已替换为标准 GPL-2.0 全文（取自 `kernelsu/kernel/LICENSE`，即上游为内核侧代码准备的那份）。

### 目录级清单

| 路径 / 产物 | 许可证 | 依据 |
|---|---|---|
| `.github/`、`tools/`、`scripts/`、`config/`、`security_patch/`、`release/` | GPL-2.0-only | 本项目自身代码 |
| `boot.img` / `AnyKernel3.zip`（构建产物） | GPL-2.0-only | Linux 6.1 + KernelSU kernel + SUSFS 补丁 |
| 构建时从 GitHub 克隆的 ReSukiSU（`KernelSU/kernel/`） | **GPL-2.0-only** | 目录内自带 `kernel/LICENSE`；最新 `main` 的源码 SPDX 实测仍为 `GPL-2.0-only`(8) / `GPL-2.0`(1)。**这是唯一被编译进内核的部分** |
| 构建时克隆的 ReSukiSU userspace（`manager/`、`js/`、`userspace/`） | GPL-3.0 | 上游 `LICENSE`，**本构建不编译** |
| 发布所附带的 ReSukiSU 管理器 APK（arm64-v8a） | **GPL-3.0** | 取自上游 Release 的已编译产物。GPL 允许再分发，源码见上游仓库同 tag |
| `kernelsu/`（仓库内置快照） | 按目录：`kernel/`+`uapi/` 为 GPL-2.0-only，其余 GPL-3.0 | **2026-10-03 起不再参与构建**（改为每次从 GitHub 拉取），保留仅为历史溯源 |
| `susfs4ksu/` | GPL-3.0 | 上游 `LICENSE` 为 GPL-3.0 |
| `susfs4ksu/kernel_patches/` | 上游未附单独声明 | 已核对上游 `50_add_susfs_in_gki-android14-6.1.patch` 原文：**整份补丁不含任何授权声明**，是纯 diff，作用于 GPL-2.0 内核 |
| `zram/lz4/` | **BSD-2-Clause** | Yann Collet, Copyright (C) 2011-2023。原目录只有源码文件头的声明、无独立许可证文件，已补充 `zram/lz4/LICENSE` |
| `device/meizu21/` | **原厂专有，未授权** | 从本机 9008 备份提取，见下方提醒 |

### 发布前仍需注意的两项

1. **`device/meizu21/` 含原厂专有二进制**（`kernel` 33.8 MB、`dtbo.img` 25 MB、
   `vendor_dlkm/*.ko` 与 `vendor_ramdisk/*.ko` 等，整个目录 168.5 MB / 1731 个文件），
   版权归魅族所有，**不建议随公开仓库分发**（有被 DMCA 下架的风险）。
   GKI 构建实际只需要该目录下的 KMI 清单与参考配置：
   `module_kmi_manifest.txt`、`Module.symvers`、`ref_stock.config`、`meizu21.info`。
2. **SUSFS 的许可证口径**：其内核补丁本身没有授权声明，而仓库 `LICENSE` 是 GPL-3.0。
   本项目按"内核补丁随 GPL-2.0 内核一同分发"的通行做法使用。若需绝对稳妥，CI 已提供两条路径：
   - `export_susfs_patches: true` —— 只导出补丁，由使用者自行合入；
   - `ksu_mode: 禁用SUSFS` —— 构建不含 SUSFS 的纯 GPL-2.0 内核。

### 其余合规要点

1. **源码提供义务**：GPL 要求分发二进制时提供对应源码。本仓库已满足 —— 完整的内置源码快照
   （`kernelsu/`、`susfs4ksu/`）+ 溯源文件（各处 `SOURCE.txt`）+ 全部补丁。
2. **随包保留许可证**：AnyKernel3 zip 内请保留其自身 LICENSE 与本文件。
3. **不包含原厂内核代码**：`boot.img` 由 AOSP ACK 编译而成，不含魅族闭源内核的任何代码；
   与原厂的关系仅为 ABI 层面的兼容性对齐（KMI 符号表、CRC、KCFI 类型哈希）。
4. **免责**：刷机有风险，因使用本构建导致的设备损坏、数据丢失由使用者自行承担。
