# 构建失败 run 15

- 时间(UTC): 2026-10-03T01:10:19Z
- 仓库/分支: FengFaQ/MEIZU21GKI @ main
- 提交: 823689ef6c89711e1f058dffb056a6eb0b79a31d
- 工作流: MEIZU21GKI 构建 (ReSukiSU + SUSFS, android14-6.1.25)
- 运行页面: https://github.com/FengFaQ/MEIZU21GKI/actions/runs/37084731787
- 变体/模式: ReSukiSU / 关闭 (SUSFS=true)
- GKI: android14-6.1.25-2023-10
- LTO: none
- extra_config: |
    # CONFIG_TRIM_UNUSED_KSYMS is not set
    # CONFIG_PANIC_ON_OOPS is not set
    # 允许 adb shell dmesg 读取内核日志(否则 user 版构建下 shell 无权读, 排障只能靠抢 512K
    # 环形缓冲区的开机瞬间 —— 本次黑屏问题正是靠这个手段才定位到 msm_kgsl 的符号 CRC 失配)。
    # 只影响权限位, 不涉及任何导出符号/KMI。
    # CONFIG_SECURITY_DMESG_RESTRICT is not set
    CONFIG_PANIC_TIMEOUT=30
    # ★ 2026-10-03: 以下 6 项恢复成原厂 12.6 第二版的取值。
    #   依据: 三个 config 全部从镜像内嵌 IKCONFIG 提取后逐行核对(不是猜的) ——
    #   device/meizu21/ref_stock.config 与 work/cfg_v2.config 只差 2 行(Jenkins 路径字符串)。
    #   · DAMON / BLK_CGROUP_IOPRIO / TMPFS_XATTR / TMPFS_POSIX_ACL: 原厂关闭, 我们之前开着。
    #     DAMON 与 PAGE_IDLE_FLAG 不只是速度问题 —— 它们会改动 struct mm_struct 字段与
    #     PG_* 页标志位编号, 而厂商模块用的是 Meizu 头文件里的偏移与常量, 存在 KMI 错位风险。
    #     PAGE_IDLE_FLAG / DAMON_VADDR / DAMON_SYSFS 无需单列: 它们由 CONFIG_DAMON select,
    #     关掉 DAMON 会一并回到原厂取值(隐藏符号直接写进 fragment 会校验失败)。
    #   · ZRAM / ZSMALLOC: 原厂内核根本没有这两项。魅族的 swap 由厂商模块提供
    #     (lsmod: smartswap_zram + smart_zsmalloc), 而 smart_zsmalloc 自己就 DEF 了全部
    #     10 个 zs_* 符号(module_kmi_manifest.txt L36876-36885), 所以内核不需要 ZSMALLOC;
    #     实测设备上 lsmod 里从没加载过 zram/zsmalloc, 我们这两项配置纯属空转差异。
    # CONFIG_DAMON is not set
    # CONFIG_BLK_CGROUP_IOPRIO is not set
    # CONFIG_TMPFS_XATTR is not set
    # CONFIG_TMPFS_POSIX_ACL is not set
    # CONFIG_ZRAM is not set
    # CONFIG_ZSMALLOC is not set
    
