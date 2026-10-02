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

## 更新内置源码

```powershell
# KernelSU (ReSukiSU)
git clone --depth 1 git@github.com:FengFaQ/ReSukiSU-fork.git tmp-ksu
robocopy tmp-ksu kernelsu /E /XD .git      # 覆盖后同步修改 kernelsu/SOURCE.txt

# SUSFS
git clone --depth 1 -b gki-android14-6.1 https://gitlab.com/simonpunk/susfs4ksu.git tmp-susfs
robocopy tmp-susfs susfs4ksu /E /XD .git   # 覆盖后同步修改 susfs4ksu/SOURCE.txt
```

改完 push 到 `main` 即自动重新构建。

---

## 刷机

产物 `AnyKernel3.zip` 用支持 AK3 的 recovery/内核管理器刷入（`anykernel.sh`：
`block=boot`、`is_slot_device=auto`、不附 dtb）。配套管理器 APK 需与 `ksu_variant` 对应
（内核按管理器 APK 的 v2 签名证书哈希识别）。

作者自担风险；救砖靠 9008 全分区备份。
