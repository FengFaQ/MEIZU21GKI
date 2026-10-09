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

