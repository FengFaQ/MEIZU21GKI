# MEIZU21GKI

魅族21（SM8650 / Qualcomm Pineapple）的 **GKI 内核**自包含构建仓库：
**ReSukiSU（+ SUSFS）+ AnyKernel3**，目标 `android14-6.1 / 6.1.25 / os_patch 2023-10`。

> 本仓库把原先分散在多个 fork 里的东西合并到一处：构建流水线、魅族21 设备树、
> KernelSU 源码（ReSukiSU）、SUSFS 补丁快照。构建时**只**联网取 Google 内核源码与几个公开工具，
> KernelSU/SUSFS 直接用仓库内的快照。

---

## 目录结构

| 路径 | 内容 |
| --- | --- |
| `.github/workflows/build.yml` | 主构建流水线（`workflow_call`，1700+ 行：源码同步/tag 回退/KSU 集成/SUSFS/defconfig/编译/AK3/失败日志/产物） |
| `.github/workflows/meizu21.yml` | **主入口**：push `main` 自动构建 + 手动 dispatch；成功 → 预览版 release + `dist` 分支 |
| `.github/workflows/meizu21-bisect.yml` | 开机循环二分定位（L0 禁用KSU / L1 禁用SUSFS / L2 全开） |
| `kernelsu/` | **内置 ReSukiSU 源码**（见 `kernelsu/SOURCE.txt`；接线方式同其官方 `kernel/setup.sh`） |
| `susfs4ksu/` | **内置 SUSFS 补丁快照** `gki-android14-6.1`（见 `susfs4ksu/SOURCE.txt`） |
| `device/meizu21/` | 魅族21 设备树快照（从本机 9008 备份提取，见 `device/meizu21/SOURCE.txt`） |
| `config/` | `stock_defconfig`（可选伪装）/ `config` / `zram.config` 等 |
| `scripts/susfs_fixes/apply.sh` | SUSFS 补丁应用脚本（含 fuzz/修偏） |
| `security_patch/` | CVE-2026-43499 rtmutex 修复链 |
| `zram/` | ZRAM LZ4/NEON 增强补丁（默认关闭） |
| `log/` | **构建失败日志**（CI 自动提交，见 `log/README.md`） |
| `tools/` | 本地校验脚本（workflow 结构断言、失败日志通道断言） |

---

## 工作流行为

**触发**：push 到 `main`（仅 workflow/config/scripts/zram/kernelsu/susfs4ksu 相关路径）或手动
`workflow_dispatch`（可选变体/SUSFS 模式/LTO/ZRAM/BBG/KPM/上传模式）。

**失败** → 自动把日志提交进仓库 `log/<run号>-run<runid>/`（含每次编译尝试的完整日志、`.rej`
冲突文件、磁盘/ccache 状态、运行页面链接）。提交 `log/**` **不会**再次触发构建。

**成功** → 自动创建 **预览版（prerelease）** release：

- `meizu21-sukisu-<run_number>`：每次构建的历史版本（只保留最近 3 个）；
- `meizu21-latest`：恒指向最新成功构建的稳定入口（同样是预览版标记）；
- 同时把产物 force-push 到 **`dist` 分支**——本机 `objects.githubusercontent.com` 不可达，
  `dist` 是取回产物的可靠通道。

**取回产物（本地）**：

```powershell
$f='<本地克隆>'
git -C $f fetch origin dist
$tmp="$env:TEMP\dist_extract"
git -C $f worktree add --detach $tmp FETCH_HEAD
Copy-Item "$tmp\*" "<目标目录>\" -Recurse      # 先 copy
git -C $f worktree remove $tmp --force         # 再 remove
```

---

## 与「可启动参考」对齐的关键配置

三方 `.config` 对比（原厂内核 / 本仓库早期构建 / 能正常启动的参考镜像 `huahuahua`）结论：

| 配置 | 原厂 | 早期构建(开机循环) | 参考(可启动) | 本仓库 |
| --- | --- | --- | --- | --- |
| `CONFIG_LTO_CLANG_THIN` / `LTO_NONE` | n / y | y / n | n / y | **`lto_mode: none`** |
| `CONFIG_TRIM_UNUSED_KSYMS` | y | y | n | **`extra_config` → 关闭** |
| `CONFIG_PANIC_ON_OOPS` / `PANIC_TIMEOUT` | y / -1 | y / -1 | n / 30 | **→ 关闭 / 30** |
| `KSU_MULTI_MANAGER_SUPPORT` | — | 缺失 | y | ReSukiSU 默认 `y` |

`meizu21.yml` 固定传 `lto_mode: "none"` 与上面三行 `extra_config`；
`build.yml` 的 `lto_mode` 默认值是 `auto`（= 历史行为：6.12→none、其余 thin），
以免影响其它机型的复用。

> ⚠️ `extra_config` 里**关闭**某个配置必须写 `# CONFIG_X is not set`，
> 写 `CONFIG_X=n` 会被 kleaf 的 fragment 校验拒绝（`actual '' != expected 'n'`）。

> 参考镜像带 `CONFIG_KSU_SUSFS_HAS_MAGIC_MOUNT=y`，而当前 ReSukiSU `main` 的 Kconfig
> 未声明该符号（其 magic 指 LSM hook magic），故本仓库暂无法开启 susfs magic mount。

---

## 实机故障的两个根因（2026-10-02 更新）

刷本仓库产物出现过两类现象，根因都已定位并修掉：

### 1) 刷入后直接进 fastboot（反复重启仍在 fastboot）

`build.yml` 的 **Android 13+ 分支**生成 boot.img 时漏了 `--os_version` / `--os_patch_level`
（Android 12 分支一直有），头部这两项为 0：

| 镜像 | os_version 字段 |
| --- | --- |
| 原厂 / 参考镜像 | `14.0.0 / 2023-10`（raw `0x1c00017a`） |
| 本仓库 run #4 | `0`（未设置） |

部分 ABL（含魅族 21）会据此判镜像非法 → 直接 fastboot。修法：13+ 分支按
`inputs.android_version` 推导 `<N>.0.0` 并写 `os_patch_level`；
另加 `boot_sign` 开关，`不签名` = 与可启动参考镜像同结构（不加 AVB footer，
只 `truncate` 零填充到 64 MiB，避免分区尾部残留上一次刷入的旧 AVB footer）。

### 2) 能到第一屏，2~3 秒后自动重启（连参考镜像也一样）

设备的模块布局决定了 release 串必须与原厂一致（否则部分模块查不到）：

| 位置 | 布局 | 受 release 串影响 |
| --- | --- | --- |
| `vendor_boot` ramdisk | `/lib/modules/*.ko` 扁平，`modules.dep` 写绝对路径 | ❌ |
| `vendor_dlkm` | `/lib/modules/*.ko` 扁平 + `modules.load`(431 项) | ❌ |
| `system_dlkm` | `/system_dlkm/lib/modules/<release>/`，`modules.load`(57 项) | ✅（内容是蓝牙/网络等） |

原厂目录名就是 `/system_dlkm/lib/modules/6.1.25-android14-11-maybe-dirty/`。
`build.yml` 在 `version` 为空时会走「KMI 伪装」分支拼出 `-android14-11-g<sha>-ab<随机>-4k`：

| 内核 | release 串 |
| --- | --- |
| 原厂（能开机） | `6.1.25-android14-11-maybe-dirty` |
| 参考镜像 | `6.1.25-Keirui-huahuahua` |
| 本仓库 run #4 | `6.1.25-android14-11-g0d89215310919-ab10017554-4k` |

修法：`meizu21.yml` / `meizu21-bisect.yml` 固定
`version: "6.1.25-android14-11-maybe-dirty"`（= 原厂 `CONFIG_LOCALVERSION`），
并在编译后新增步骤**硬校验**版本串，不一致直接 fail，避免再产出「刷了必挂」的包。

> ⚠️ 注意：release 串**不足以单独解释**「卡第一屏 2~3 秒后重启」——`vendor_boot`/`vendor_dlkm`
> 的模块是扁平绝对路径，与 release 无关。重启的可疑顺序是：
> ① `modules.load` 里某模块加载失败（缺符号 / CRC 不一致）→ 第一阶段 init FATAL → 重启；
> ② KSU/SUSFS 补丁在早期引导崩（用 `meizu21-bisect` 的 L1/L0 区分）；③ 其他。
> 判据看下面 KMI 校验的 `module_compat.txt`。

> 注：模块 `.modinfo` 里的 vermagic 是 `6.1.25 SMP preempt mod_unload modversions aarch64`
> （不带 localversion）。内核 `same_magic()` 在模块带 `__versions`（`CONFIG_MODVERSIONS=y`）时
> 只比对第一个空格之后的部分，所以**版本串不参与模块校验，符号 CRC 才是真校验**。

### 不刷机验证「模块能不能加载」

`device/meizu21/module_kmi_manifest.txt` 是从设备真实 `.ko`（vendor_boot ramdisk 392 个模块）
抽出的 KMI 依赖清单（3937 个符号，其中 2927 个必须由内核提供）。CI 编译后会用内核
`Module.symvers` 校验这些符号**存在且 CRC 一致**，报告写入 `module_compat.txt`
（随 release / dist 分支上传；`Module.symvers` 也一并上传便于离线核对）。
`RESULT: FAIL` 就说明内核会拒载厂商模块，不必浪费一次刷机。

---

## KernelSU 源码来源（2026-10-03 起的硬规则）

**每次编译都从 GitHub 现场拉取 ReSukiSU，不再使用仓库内置的 `kernelsu/`。**

```
默认: git clone https://github.com/ReSukiSU/ReSukiSU  然后 checkout main
```

这样做的目的：内核自带的 SUSFS 支持与 apk 签名/版本校验**始终对上最新版管理器 APK**。
内置快照会随上游推进而落后（实测内置的 `34210a4d` 已落后上游 `main`，上游 tag 已到
`v4.2.0-rc3`），用它等于把管理器版本钉死。

拉最新不会影响 SUSFS：ReSukiSU 的 SUSFS 是**内置**的 —— `scripts/susfs_fixes/apply.sh` 里
只有 `Official` 变体才打 `10_enable_susfs_for_ksu.patch`；而内核侧的
`50_add_susfs_in_gki-*.patch` 作用于 ACK 内核树，与 KernelSU 版本无关。已核对最新 ReSukiSU
仍提供我们启用的全部 10 个 `CONFIG_KSU_SUSFS_*` 选项。

**要钉版本时不用改代码** —— 到仓库 `Settings → Secrets and variables → Actions → Variables`
设两个变量即可：

| 变量 | 默认 | 说明 |
|---|---|---|
| `KSU_REPO` | `https://github.com/ReSukiSU/ReSukiSU` | 换仓库 |
| `KSU_REF` | `main` | 钉到 tag/commit，例如 `v4.1.0`。设了它，发布时会配套取该 tag 的管理器 APK |

`kernelsu/` 目录仍留在仓库里，但**已不参与构建**（仅作历史溯源与离线参考）。

---

## 配套管理器 APK

发布时会自动从上游 ReSukiSU 的**最新 Release**取 `arm64-v8a` 版管理器 APK 一并上传
（上游同时提供 `armeabi-v7a` / `universal` / `x86_64`，只取真机用的 arm64-v8a）。
APK 会同时进入 `meizu21-latest` 与 `dist` 分支，因此本机被墙也能通过 dist 分支取到。

注意上游目前发布的都是 rc 预发布，而 `/releases/latest` 会跳过预发布（实测返回 404），
所以取的是发布列表里的最新一条；若设了 `KSU_REF=<tag>`，则优先取该 tag 的发布。
取不到时只告警、不阻塞内核发布，并在 release 说明里写明"请自行下载"。

管理器 APK 的许可证是 **GPL-3.0**（上游 `ReSukiSU/ReSukiSU`），源码同仓库可得。

---

## 更新内置源码

`kernelsu/`（ReSukiSU）已不再参与构建，通常不需要更新。只有 `susfs4ksu/` 仍需保持最新：

```powershell
# SUSFS —— 内置快照优先, 缺失才联网克隆
git clone --depth 1 -b gki-android14-6.1 https://gitlab.com/simonpunk/susfs4ksu.git tmp-susfs
robocopy tmp-susfs susfs4ksu /E /XD .git   # 覆盖后同步修改 susfs4ksu/SOURCE.txt
```

改完 push 到 `main` 即自动重新构建。（`kernelsu/` 若确实要更新，命令同前，但构建不会用到它。）

---

## 刷机

产物 `AnyKernel3.zip` 用支持 AK3 的 recovery/内核管理器刷入（`anykernel.sh`：
`block=boot`、`is_slot_device=auto`、不附 dtb）。配套管理器 APK 需与 `ksu_variant` 对应
（内核按管理器 APK 的 v2 签名证书哈希识别）。

作者自担风险；救砖靠 9008 全分区备份。

---

## 许可证

本项目自身代码（工作流、构建脚本、工具、文档）采用 **GPL-2.0-only**，与它所构建的 Linux 内核一致。
完整条款见仓库根目录的 [`LICENSE`](LICENSE)。

构建产物 `boot.img` / `AnyKernel3.zip` 同样是 **GPL-2.0-only** —— 由 Linux 6.1（GPL-2.0-only）
+ KernelSU kernel 部分（GPL-2.0-only）+ SUSFS 内核补丁组成。

仓库内另含若干第三方组件，各自保留其原有许可证：`kernelsu/` 的 userspace 部分与 `susfs4ksu/`
为 GPL-3.0，`zram/lz4/` 为 BSD-2-Clause。**逐目录的完整清单、固定版本号与发布注意事项
见 [`CREDITS.md`](CREDITS.md)。**
