# android_device_meizu_meizu21-kernel

魅族 21(SM8650 / Qualcomm Pineapple,GKI **android14-6.1**)的内核设备树,
**预编译内核 drop** 风格,结构参照 `android_device_meizu_meizu21Pro-kernel`(Paranoid Android)。

## 来源

全部产物提取自本机 9008 全分区备份(MEIZUBOX ParBak,固件 2026.05.04):

| 目录/文件 | 提取自 | 说明 |
| --- | --- | --- |
| `kernel` | `boot_a.img` → unpack_bootimg | GKI arm64 Image(带 EFI stub) |
| `dtb/` | `vendor_boot_a.img` → dtb → extract_dtb | Pineapple SoC + v2,共 2 个 |
| `dtbo.img` | `dtbo_a.img` 原样拷贝 | Android DTBO 镜像 |
| `vendor_ramdisk/` | `vendor_boot_a.img` → vendor_ramdisk00(LZ4 legacy → cpio) | 335 个 .ko + modules.* 元数据 |
| `vendor_dlkm/` | `super.img` → lpunpack → vendor_dlkm_a(EROFS) | 304 个 .ko + modules.* |
| `system_dlkm/` | `super.img` → lpunpack → system_dlkm_a(EROFS) | 57 个 .ko(嵌套 kernel/… 结构)+ modules.* |
| `kernel-headers/` | 继承自 21Pro drop(QTI 显示内核头) | Android.bp 引用 |
| `extras/` | vendor_ramdisk/bootconfig | fstab.qcom、boot 头参数存档 |

设备身份(取自 vendor_dlkm build.prop):`meizu21` / MEIZU 21 / `meizu_21_CN`,
内核版本 **6.1.25-android14-11-maybe-dirty**(与 21Pro 的 KMI 相同,内容不同)。

## extract-files.sh(重新提取)

```bash
./extract-files.sh <9008镜像目录>   # 例: /e/shuji/MEI/ToolsBox/9008/meizu21_.../images
```

依赖:同仓库 `../tools/`(lpunpack、extract.erofs、unpack_bootimg.py、extract_dtb.py)、
`python3 + lz4`(pip)、7z。流程 = 解包 boot/vendor_boot → 拆 dtb → 解 vendor_ramdisk
(LZ4 legacy)→ lpunpack super → 解 EROFS 的 vendor_dlkm/system_dlkm → 汇总。
也可直接阅读脚本按步骤手动执行(Windows pwsh 亦已验证可行)。

## 用途

1. 作为魅族21 GKI 内核开发的基线设备树(内核/模块/DTB 参照物)。
2. 接入 `GKI_KernelSU_SUSFS` 工作流构建 KSU+SUSFS 内核 → AnyKernel3 刷入
   (KMI 相同版本可直接刷;boot.img 路线:`mkbootimg --header_version 4` + avbtool)。
